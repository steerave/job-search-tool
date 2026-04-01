"""
profile_generator.py

Sends user feedback data to Claude to generate a nuanced target role profile.
The profile is written to profile/target_role_profile.md and used by fit_scorer.py.
"""

import logging

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an expert career advisor analyzing a job seeker's feedback patterns.
Your job is to synthesize their scoring, notes, and application history into a clear,
actionable target role profile. Be specific and evidence-based."""

PROFILE_PROMPT_TEMPLATE = """You are an expert career advisor analyzing a job seeker's feedback to build their ideal role profile.

{current_profile_section}

JOB TRACKER FEEDBACK (roles the user has scored and commented on):
{tracker_text}

APPLICATION HISTORY (roles the user has actually applied for):
{status_text}

Based on this data, generate an updated target role profile in markdown format.

The profile should capture:
- Ideal role titles and seniority level
- Preferred industries and company types
- Domain preferences (e.g., SaaS, AI/ML, digital transformation)
- Key skills and responsibilities the user gravitates toward
- Work arrangement preferences (remote, hybrid, location)
- Compensation expectations
- Patterns in what the user rates highly vs. poorly
- Patterns in what the user actually applies for vs. skips
- Nuanced preferences that keywords alone cannot capture

Be specific and evidence-based. Reference actual roles and scores from the data.
Format as a clean markdown document with sections."""


def format_tracker_for_prompt(tracker_data: list) -> str:
    """Format tracker feedback data into readable text for the prompt."""
    if not tracker_data:
        return "No feedback data available yet."

    lines = []
    for row in tracker_data:
        line = f"- {row['role_name']} @ {row['company']}"
        line += f" | AI Score: {row['fit_score']}/10"
        if row['my_score'] is not None:
            line += f" | My Score: {row['my_score']}/5"
        if row['remote']:
            line += f" | Remote: {row['remote']}"
        if row['compensation']:
            line += f" | Comp: {row['compensation']}"
        if row['location']:
            line += f" | Location: {row['location']}"
        if row['status']:
            line += f" | Status: {row['status']}"
        if row['notes']:
            line += f"\n  Notes: {row['notes']}"
        if row['fit_notes']:
            line += f"\n  AI Notes: {row['fit_notes']}"
        lines.append(line)
    return "\n".join(lines)


def format_status_for_prompt(status_data: list) -> str:
    """Format application history into readable text for the prompt."""
    if not status_data:
        return "No application history available yet."

    lines = []
    for row in status_data:
        line = f"- {row['role_title']} @ {row['company']}"
        if row['industry']:
            line += f" | Industry: {row['industry']}"
        if row['compensation_range']:
            line += f" | Comp: {row['compensation_range']}"
        if row['remote_only']:
            line += f" | Remote: {row['remote_only']}"
        if row['applied']:
            line += f" | Applied: {row['applied']}"
        if row['status']:
            line += f" | Status: {row['status']}"
        if row['notes']:
            line += f"\n  Notes: {row['notes']}"
        lines.append(line)
    return "\n".join(lines)


def build_profile_prompt(
    tracker_data: list,
    status_data: list,
    current_profile: str,
) -> str:
    """Assemble the full prompt for Claude."""
    if current_profile:
        current_section = f"CURRENT TARGET PROFILE (update and refine this):\n{current_profile}"
    else:
        current_section = "CURRENT TARGET PROFILE:\nNo existing profile — this is the first generation."

    return PROFILE_PROMPT_TEMPLATE.format(
        current_profile_section=current_section,
        tracker_text=format_tracker_for_prompt(tracker_data),
        status_text=format_status_for_prompt(status_data),
    )


def generate_target_profile(
    tracker_data: list,
    status_data: list,
    current_profile: str,
    client,
) -> str:
    """
    Call Claude to generate an updated target role profile.

    Args:
        tracker_data: Parsed tracker feedback rows
        status_data: Parsed job status rows
        current_profile: Current profile markdown (empty string if none)
        client: anthropic.Anthropic client instance

    Returns:
        Markdown string with the updated target role profile
    """
    prompt = build_profile_prompt(tracker_data, status_data, current_profile)

    logger.info("Generating target role profile via Claude...")
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        profile_text = response.content[0].text.strip()
        logger.info(f"Generated profile: {len(profile_text)} chars")
        return profile_text
    except Exception as e:
        logger.error(f"Profile generation failed: {e}")
        return "Profile generation failed — using previous profile if available."
