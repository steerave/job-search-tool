"""
fit_scorer.py

Uses Claude API to score how well a job matches the user's profile.
Returns a score 1-10 with a rationale string.

Prompt caching: the candidate profile is sent as a cached system prompt block.
Only the job description changes per call — reducing input token costs ~85%
after the first call in each batch.
"""

import json
import logging
import time
from pathlib import Path

from api_cost_logger import log_api_cost

logger = logging.getLogger(__name__)


class BillingError(Exception):
    """Raised when the Anthropic API rejects a call due to insufficient credits.
    Signals the batch loop to abort immediately — retrying is pointless and wastes time.
    """


def _load_target_profile() -> str:
    """Load target role profile if it exists. Returns empty string if not found."""
    profile_path = Path(__file__).parent.parent / "profile" / "target_role_profile.md"
    if profile_path.exists():
        return profile_path.read_text(encoding="utf-8")
    return ""


MODEL = "claude-sonnet-4-6"

CACHED_SYSTEM_TEMPLATE = """You are an expert career advisor and job fit analyst.
Evaluate how well a candidate's profile matches a job description.
Be honest, specific, and concise. Focus on skills, experience level, and domain alignment.

CANDIDATE PROFILE:
Name: {name}
Headline: {headline}
Summary: {summary}

Skills: {skills}

Experience:
{experience_text}

Education:
{education_text}

{target_role_profile}---

INSTRUCTIONS:
Rate how well this candidate matches the job description on a scale of 1-10.

Respond ONLY with a JSON object in this exact format:
{{"score": <integer 1-10>, "rationale": "<2-3 sentences: key matches, key gaps, overall verdict>"}}

Scoring guide:
9-10: Exceptional match — candidate meets nearly all requirements, strong domain fit
7-8: Good match — candidate meets most requirements, minor gaps
5-6: Moderate match — candidate meets core requirements, notable gaps
3-4: Weak match — significant skill or experience gaps
1-2: Poor match — fundamentally different background

Agency experience bonus: If the job description explicitly prefers or requires marketing agency
or digital agency experience, treat the candidate's agency background (R/GA, AKQA, Verndale)
as a strong positive signal and increase the score accordingly. Note this match in the rationale.

Be specific in the rationale. Name actual skills/technologies that match or are missing."""

JOB_PROMPT_TEMPLATE = """JOB POSTING:
Title: {job_title}
Company: {company}
Location: {location}
Type: {job_type}
Compensation: {salary}

Description:
{job_description}"""


def _build_profile_text(profile: dict) -> dict:
    """Format profile fields for the cached system prompt."""
    skills_text = ", ".join(profile.get("skills", [])) or "Not specified"

    experience_parts = []
    for exp in profile.get("experience", [])[:5]:  # Top 5 roles
        title = exp.get("title", "Unknown Role")
        company = exp.get("company", "")
        role_line = f"- {title}"
        if company:
            role_line += f" @ {company}"
        started = exp.get("started_on", "")
        finished = exp.get("finished_on", "Present")
        if started:
            role_line += f" ({started} – {finished})"
        experience_parts.append(role_line)
        for bullet in exp.get("bullets", [])[:3]:  # Top 3 bullets per role
            if bullet.strip():
                experience_parts.append(f"  • {bullet.strip()}")
    experience_text = "\n".join(experience_parts) or "Not specified"

    education_parts = []
    for edu in profile.get("education", []):
        degree = edu.get("degree", "")
        field = edu.get("field", "")
        school = edu.get("school", "")
        end = edu.get("end_date", "")
        parts = [p for p in [degree, field] if p]
        edu_line = " in ".join(parts) if parts else "Degree"
        if school:
            edu_line += f" — {school}"
        if end:
            edu_line += f" ({end})"
        education_parts.append(edu_line)
    education_text = "\n".join(f"- {e}" for e in education_parts) or "Not specified"

    return {
        "skills": skills_text,
        "experience_text": experience_text,
        "education_text": education_text,
    }


def build_cached_system_prompt(profile: dict) -> str:
    """
    Build the system prompt that contains the candidate profile.
    Called once per batch — the result is passed to every score_job call
    so it can be sent with cache_control and reused across calls.
    """
    profile_texts = _build_profile_text(profile)

    target_profile = _load_target_profile()
    if target_profile:
        target_section = (
            "TARGET ROLE PREFERENCES (learned from candidate's own feedback and application history):\n"
            f"{target_profile}\n\n"
            "Use these preferences to inform your scoring. A role that matches the candidate's\n"
            "stated preferences should score higher than one that only matches on paper qualifications.\n\n"
        )
    else:
        target_section = ""

    return CACHED_SYSTEM_TEMPLATE.format(
        name=profile.get("name", "Candidate"),
        headline=profile.get("headline", ""),
        summary=(profile.get("summary", "")[:500] if profile.get("summary") else ""),
        skills=profile_texts["skills"],
        experience_text=profile_texts["experience_text"],
        education_text=profile_texts["education_text"],
        target_role_profile=target_section,
    )


def score_job(job: dict, cached_system: str, client) -> dict:
    """
    Score a single job against the candidate profile using the Claude API.

    Args:
        job: Job dict from scraper
        cached_system: Pre-built system prompt string (from build_cached_system_prompt).
                       Sent with cache_control so it's only charged once per batch.
        client: anthropic.Anthropic client instance

    Returns:
        dict with keys: score (int), rationale (str)
    """
    from job_scraper import format_salary

    salary = format_salary(job) if job else ""

    description = job.get("description", "")
    if len(description) > 3000:
        description = description[:3000] + "...[truncated]"

    job_prompt = JOB_PROMPT_TEMPLATE.format(
        job_title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        job_type=job.get("job_type", ""),
        salary=salary,
        job_description=description,
    )

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=300,
                system=[
                    {
                        "type": "text",
                        "text": cached_system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": job_prompt}],
            )
            log_api_cost("fit_scorer", MODEL, response.usage)
            raw = response.content[0].text.strip()

            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            result = json.loads(raw)
            score = int(result.get("score", 5))
            score = max(1, min(10, score))
            rationale = str(result.get("rationale", "")).strip()

            logger.info(f"Scored '{job.get('title')}' @ '{job.get('company')}': {score}/10")
            return {"score": score, "rationale": rationale}

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}\nRaw: {raw[:200]}")
            if attempt < 2:
                time.sleep(2)
        except Exception as e:
            error_str = str(e)
            # Billing errors are permanent — retrying burns time and won't help
            if "credit balance is too low" in error_str or "insufficient_balance" in error_str:
                raise BillingError(
                    "Anthropic API credit balance too low. Add credits at console.anthropic.com."
                ) from e
            logger.error(f"Claude API error on attempt {attempt + 1}: {e}")
            if attempt < 2:
                time.sleep(5)

    logger.error(f"Failed to score job after 3 attempts: {job.get('title')} @ {job.get('company')}")
    return None


def score_jobs_batch(jobs: list[dict], profile: dict, client) -> list[dict]:
    """
    Score multiple jobs. Builds the cached system prompt once and reuses it
    across all calls in the batch. Returns each job dict enriched with
    'fit_score' and 'fit_notes'.
    """
    cached_system = build_cached_system_prompt(profile)
    logger.info(f"Prompt caching enabled — profile system prompt built once for {len(jobs)} jobs")

    scored = []
    skipped = 0
    for i, job in enumerate(jobs):
        logger.info(f"Scoring job {i+1}/{len(jobs)}: {job.get('title')} @ {job.get('company')}")
        try:
            result = score_job(job, cached_system, client)
        except BillingError as e:
            logger.error(f"BILLING ERROR — aborting scoring batch: {e}")
            logger.warning(
                f"Scoring aborted after {i}/{len(jobs)} jobs. "
                f"Add credits at console.anthropic.com and re-run."
            )
            break
        if result is None:
            skipped += 1
            logger.warning(f"Skipping job (scoring failed): {job.get('title')} @ {job.get('company')}")
            continue
        job["fit_score"] = result["score"]
        job["fit_notes"] = result["rationale"]
        scored.append(job)
        if i < len(jobs) - 1:
            time.sleep(0.5)

    if skipped:
        logger.warning(f"Scoring complete: {len(scored)} scored, {skipped} skipped due to API errors")
    return scored
