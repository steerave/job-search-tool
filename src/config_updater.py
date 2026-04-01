"""
config_updater.py

Uses Claude to suggest config.yaml changes based on user feedback.
Applies asymmetric rules: aggressive on adding, conservative on removing.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an expert career advisor analyzing a job seeker's feedback
to suggest search configuration improvements. Be conservative on removals
and aggressive on discovering new search terms."""

CONFIG_PROMPT_TEMPLATE = """You are analyzing a job seeker's feedback to suggest search configuration improvements.

CURRENT CONFIG:
Job Titles: {job_titles}
Required Keywords: {required_keywords}
Exclude Keywords: {exclude_keywords}

JOB TRACKER FEEDBACK:
{tracker_text}

APPLICATION HISTORY:
{status_text}

Suggest changes to the job search configuration. You MUST follow these rules:

ADDING (low threshold — be aggressive):
- Suggest new job_titles if 2+ applied roles or 2+ high-scored roles (My Score 4-5) share a title pattern not already in the search
- Suggest new required_keywords if a positive theme recurs in high-scored roles or applied roles
- Suggest new exclude_keywords ONLY if the user explicitly requests exclusion in their Notes (look for phrases like "exclude", "stop showing", "remove", "don't search for", "irrelevant")

REMOVING (high threshold — almost never):
- Suggest removing a job_title ONLY if the user explicitly says to stop searching for it in their Notes
- NEVER suggest removing required_keywords automatically
- NEVER suggest removing exclude_keywords

For roles that match poorly but aren't explicitly excluded by the user:
- Do NOT suggest removing them from the search
- Instead, note them so the target role profile can lower their fit score

Respond ONLY with a JSON object:
{{
  "add_job_titles": ["title1", "title2"],
  "remove_job_titles": [],
  "add_required_keywords": ["keyword1"],
  "add_exclude_keywords": [],
  "reasoning": {{
    "title1": "why this title is being added",
    "keyword1": "why this keyword is being added"
  }}
}}

Only include non-empty arrays. If no changes are warranted, return an empty object {{}}.
Do NOT include keys with empty arrays."""


def build_config_prompt(
    tracker_data: list,
    status_data: list,
    current_config: dict,
) -> str:
    """Assemble the config suggestion prompt."""
    from profile_generator import format_tracker_for_prompt, format_status_for_prompt

    return CONFIG_PROMPT_TEMPLATE.format(
        job_titles="\n".join(f"  - {t}" for t in current_config.get("job_titles", [])),
        required_keywords="\n".join(f"  - {k}" for k in current_config.get("required_keywords", [])),
        exclude_keywords="\n".join(f"  - {k}" for k in current_config.get("exclude_keywords", [])),
        tracker_text=format_tracker_for_prompt(tracker_data),
        status_text=format_status_for_prompt(status_data),
    )


def parse_config_suggestions(raw: str) -> dict:
    """Parse Claude's JSON response into a suggestions dict."""
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse config suggestions: {raw[:200]}")
        return {}


def generate_config_suggestions(
    tracker_data: list,
    status_data: list,
    current_config: dict,
    client,
) -> dict:
    """Call Claude to get config change suggestions."""
    prompt = build_config_prompt(tracker_data, status_data, current_config)

    logger.info("Generating config suggestions via Claude...")
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        suggestions = parse_config_suggestions(raw)
        logger.info(f"Config suggestions: {json.dumps(suggestions, indent=2)}")
        return suggestions
    except Exception as e:
        logger.error(f"Config suggestion generation failed: {e}")
        return {}


def apply_config_updates(config_path: str, suggestions: dict) -> list:
    """
    Apply additions/removals to config.yaml using ruamel.yaml to preserve comments.
    Returns a list of human-readable change descriptions.
    """
    yaml = YAML()
    yaml.preserve_quotes = True

    with open(config_path, encoding="utf-8") as f:
        config = yaml.load(f)

    changes = []

    # Add job titles
    for title in suggestions.get("add_job_titles", []):
        existing = [str(t).lower() for t in config.get("job_titles", [])]
        if title.lower() not in existing:
            config["job_titles"].append(title)
            changes.append(f'ADDED job_title: "{title}"')

    # Remove job titles (only from explicit user request)
    for title in suggestions.get("remove_job_titles", []):
        titles = config.get("job_titles", [])
        for i, existing in enumerate(titles):
            if str(existing).lower() == title.lower():
                titles.pop(i)
                changes.append(f'REMOVED job_title: "{title}"')
                break

    # Add required keywords
    for kw in suggestions.get("add_required_keywords", []):
        existing = [str(k).lower() for k in config.get("required_keywords", [])]
        if kw.lower() not in existing:
            config["required_keywords"].append(kw)
            changes.append(f'ADDED required_keyword: "{kw}"')

    # Add exclude keywords (only from explicit user request)
    for kw in suggestions.get("add_exclude_keywords", []):
        existing = [str(k).lower() for k in config.get("exclude_keywords", [])]
        if kw.lower() not in existing:
            config["exclude_keywords"].append(kw)
            changes.append(f'ADDED exclude_keyword: "{kw}"')

    if changes:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)
        logger.info(f"Applied {len(changes)} config changes")

    return changes


def log_config_changes(log_path: str, changes: list, reasoning: dict) -> None:
    """Append config changes to the audit log."""
    if not changes:
        return

    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    for change in changes:
        lines.append(f"[{timestamp}] {change}")
        for key, reason in reasoning.items():
            if key.lower() in change.lower():
                lines.append(f"  Reason: {reason}")
                break

    with open(p, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")

    logger.info(f"Logged {len(changes)} config changes to {log_path}")
