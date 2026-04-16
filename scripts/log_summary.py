#!/usr/bin/env python3
"""
log_summary.py

Reads a pipeline log file and prints a compact run summary with cost estimate.
Used by the diagnose-run Claude Code skill and as a standalone diagnostic tool.

Usage:
    python scripts/log_summary.py              # today's log
    python scripts/log_summary.py 2026-04-16   # specific date
"""

import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "logs"

# Sonnet 4.6 pricing (per token)
_INPUT = 3.0 / 1_000_000       # $3 per million input tokens
_CACHED = 0.30 / 1_000_000     # $0.30 per million cached read tokens
_OUTPUT = 15.0 / 1_000_000     # $15 per million output tokens

# Approximate token counts per call (based on measured prompt sizes)
_AVG_SYSTEM_TOKENS = 1500   # cached system prompt (candidate profile)
_AVG_JOB_TOKENS = 500       # per-job user message (title + description excerpt)
_AVG_OUTPUT_TOKENS = 150    # per response


def parse_log_text(text: str) -> dict:
    """
    Extract pipeline metrics from a log file's text content.
    Returns a dict with all metrics needed by format_summary.
    All counts default to 0 / False if not found in the log.
    """
    def find_int(pattern: str) -> int:
        m = re.search(pattern, text)
        return int(m.group(1)) if m else 0

    national = find_int(r'\[National Remote\] Total after filtering: (\d+) jobs')
    local = find_int(r'\[Local QC\] Total after filtering: (\d+) jobs')
    watchlist = find_int(r'\[Watchlist\] Total after filtering: (\d+) jobs')
    loc_removed = find_int(r'\[Local QC\] Location filter: (\d+) non-local jobs removed')

    scraped = find_int(r'Scraped:\s+(\d+)')
    new = find_int(r'New \(unseen\):\s+(\d+)')
    added = find_int(r'Added to sheet:\s+(\d+)')
    below = find_int(r'Below threshold:\s+(\d+)')

    domain_skipped = find_int(r'Domain pre-filter: (\d+) off-domain jobs skipped')

    cap_match = re.search(r'Job count \((\d+)\) exceeds max_jobs_to_score=(\d+)', text)
    cap_hit = cap_match is not None
    cap_truncated = (int(cap_match.group(1)) - int(cap_match.group(2))) if cap_match else 0

    error_lines = re.findall(r'\[ERROR\].*', text)

    return {
        "national": national,
        "local": local,
        "watchlist": watchlist,
        "loc_removed": loc_removed,
        "scraped": scraped,
        "new": new,
        "added": added,
        "below": below,
        "scored": added + below,
        "domain_skipped": domain_skipped,
        "cap_hit": cap_hit,
        "cap_truncated": cap_truncated,
        "error_count": len(error_lines),
        "error_lines": error_lines,
    }


def estimate_cost(scored: int) -> float:
    """
    Estimate Claude API cost for a batch of scored jobs.
    Assumes prompt caching is active: first call pays full system token price,
    subsequent calls pay cached read rate for the system prompt.
    """
    if scored <= 0:
        return 0.0
    first_call = (
        (_AVG_SYSTEM_TOKENS + _AVG_JOB_TOKENS) * _INPUT
        + _AVG_OUTPUT_TOKENS * _OUTPUT
    )
    if scored == 1:
        return first_call
    rest_per_call = (
        _AVG_SYSTEM_TOKENS * _CACHED
        + _AVG_JOB_TOKENS * _INPUT
        + _AVG_OUTPUT_TOKENS * _OUTPUT
    )
    return first_call + (scored - 1) * rest_per_call


def format_summary(stats: dict, log_date: str) -> str:
    """Format parsed stats into a human-readable summary string."""
    lines = [f"=== Run Summary {log_date} ==="]

    lines.append(
        f"Scraped:        {stats['scraped']:>4}  "
        f"(national: {stats['national']}, local: {stats['local']}, "
        f"watchlist: {stats['watchlist']})"
    )

    if stats["loc_removed"]:
        lines.append(
            f"  Local filter: {stats['loc_removed']:>4} non-local removed"
        )

    lines.append(f"Duplicates:     {stats['new']:>4} new  |  rest were duplicates")

    if stats["domain_skipped"]:
        lines.append(
            f"Domain filter:  {stats['domain_skipped']:>4} off-domain titles skipped"
        )

    cap_note = (
        f"  [CAP HIT — {stats['cap_truncated']} dropped]"
        if stats["cap_hit"] else ""
    )
    lines.append(f"Scored:         {stats['scored']:>4}{cap_note}")
    lines.append(
        f"  -> Sheet: {stats['added']:>3}  |  Below threshold: {stats['below']:>3}"
    )

    cost = estimate_cost(stats["scored"])
    lines.append(
        f"Est. API cost:  ${cost:.3f}  (~{stats['scored']} calls, caching active)"
    )

    if stats["error_count"]:
        lines.append(f"Errors:         {stats['error_count']}")
        for line in stats["error_lines"][:3]:
            lines.append(f"  ! {line[:120]}")
        if stats["error_count"] > 3:
            lines.append(f"  ... ({stats['error_count'] - 3} more)")
    else:
        lines.append("Errors:         0")

    return "\n".join(lines)


def main() -> None:
    log_date = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    log_path = LOG_DIR / f"{log_date}.log"

    if not log_path.exists():
        print(f"No log found for {log_date} ({log_path})")
        sys.exit(0)

    text = log_path.read_text(encoding="utf-8", errors="replace")
    stats = parse_log_text(text)
    print(format_summary(stats, log_date))


if __name__ == "__main__":
    main()
