"""
main.py

Entry point for the Job Search Automation Tool.
Orchestrates the full pipeline: scrape -> deduplicate -> score -> update sheets -> email.

Usage:
    python main.py              # Full run
    python main.py --dry-run    # Scrape + score only, no writes
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure src/ is on the path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# Logging setup (must happen before any other imports that use logging)
# ---------------------------------------------------------------------------
def setup_logging(log_dir: str, log_level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / f"{date.today().isoformat()}.log"

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config & env loading
# ---------------------------------------------------------------------------
def load_config(config_path: str) -> dict:
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required: pip install PyYAML")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_env(env_path: str = ".env") -> None:
    try:
        from dotenv import load_dotenv
        # override=True ensures .env wins over any pre-existing (possibly empty)
        # env var inherited from the launching shell. Task Scheduler runs are
        # unaffected (clean env); only manual runs in shells with pre-set vars
        # benefit. Without this, manual runs silently fail if e.g.
        # ANTHROPIC_API_KEY="" exists in the parent environment.
        load_dotenv(env_path, override=True)
    except ImportError:
        logger.warning("python-dotenv not installed - reading from system environment only")


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------
def get_anthropic_client():
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
    return anthropic.Anthropic(api_key=api_key)


def get_sheets_updater(config: dict):
    from sheets_updater import SheetsUpdater, BELOW_SHEET
    sheets_id = os.getenv("GOOGLE_SHEETS_ID")
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sheets_id or not sa_path:
        raise ValueError("GOOGLE_SHEETS_ID and GOOGLE_SERVICE_ACCOUNT_JSON must be set in .env")
    updater = SheetsUpdater(sheets_id=sheets_id, service_account_path=sa_path)
    updater.connect()
    return updater


def _filter_scoreable_jobs(jobs: list[dict], config: dict) -> tuple[list[dict], list[dict]]:
    """
    Pre-scoring filter: keep only jobs whose title contains at least one domain word.
    Domain words are configured in config.yaml under title_domain_words.
    Returns (scoreable, skipped). If title_domain_words is empty, all jobs are scoreable.
    """
    domain_words = [w.lower() for w in config.get("title_domain_words", [])]
    if not domain_words:
        return jobs, []

    scoreable = []
    skipped = []
    for job in jobs:
        title_lower = job.get("title", "").lower()
        if any(word in title_lower for word in domain_words):
            scoreable.append(job)
        else:
            logger.info(
                f"Pre-filter: off-domain title skipped — '{job['title']}' @ {job['company']}"
            )
            skipped.append(job)
    return scoreable, skipped


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_pipeline(config: dict, dry_run: bool = False, no_age_filter: bool = False) -> dict:
    """
    Full pipeline execution.
    Returns a summary dict for reporting.
    """
    from job_scraper import scrape_all_jobs
    from deduplicator import load_seen_jobs, filter_new_jobs, mark_jobs_seen, save_seen_jobs, prune_old_entries
    from fit_scorer import score_jobs_batch
    from profile_parser import load_profile
    from email_notifier import send_digest_from_env
    from sheets_updater import SheetsUpdater, BELOW_SHEET

    errors = []
    summary = {
        "scraped": 0,
        "new": 0,
        "duplicates": 0,
        "above_threshold": 0,
        "skipped_below_threshold": 0,
        "errors": errors,
    }

    # --- Load profile ---
    profile_path = str(PROJECT_ROOT / "profile" / "parsed_profile.json")
    try:
        profile = load_profile(profile_path)
        logger.info(f"Loaded profile: {profile.get('name', 'Unknown')}")
    except FileNotFoundError:
        logger.error(f"Profile not found at {profile_path}. Run setup.py first.")
        errors.append("Profile not found - run setup.py")
        if not dry_run:
            return summary
        profile = {}

    # --- Scrape ---
    logger.info("=" * 60)
    logger.info("STEP 1: Scraping jobs...")
    logger.info("=" * 60)
    if no_age_filter:
        logger.info("*** NO AGE FILTER - scraping all open positions regardless of post date ***")
        config = dict(config)
        config["national_remote"] = dict(config.get("national_remote", {}))
        config["national_remote"]["max_age_hours"] = 17520  # 2 years
        config["local_qc"] = dict(config.get("local_qc", {}))
        config["local_qc"]["max_age_hours"] = 17520
    try:
        all_jobs = scrape_all_jobs(config)
        summary["scraped"] = len(all_jobs)
    except Exception as e:
        logger.error(f"Job scraping failed: {e}")
        errors.append(f"Scraping failed: {e}")
        all_jobs = []

    if not all_jobs:
        logger.info("No jobs scraped - nothing to process")
        if not dry_run:
            send_digest_from_env([], 0, 0, errors)
        return summary

    # --- Deduplicate ---
    logger.info("=" * 60)
    logger.info("STEP 2: Deduplicating...")
    logger.info("=" * 60)
    seen_jobs_path = str(PROJECT_ROOT / "data" / "seen_jobs.json")
    retention_days = config.get("seen_jobs_retention_days", 90)

    seen = load_seen_jobs(seen_jobs_path)
    seen = prune_old_entries(seen, retention_days)
    new_jobs, duplicates = filter_new_jobs(all_jobs, seen)
    summary["new"] = len(new_jobs)
    summary["duplicates"] = len(duplicates)
    logger.info(f"New: {len(new_jobs)} | Duplicates skipped: {len(duplicates)}")

    if not new_jobs:
        logger.info("No new jobs found after deduplication")
        if not dry_run:
            send_digest_from_env([], 0, len(duplicates), errors)
        return summary

    # --- Pre-scoring filter ---
    logger.info("=" * 60)
    logger.info("STEP 3: Pre-scoring filter...")
    logger.info("=" * 60)
    scoreable_jobs, domain_skipped = _filter_scoreable_jobs(new_jobs, config)
    if domain_skipped:
        logger.info(
            f"Domain pre-filter: {len(domain_skipped)} off-domain jobs skipped, "
            f"{len(scoreable_jobs)} remain for scoring"
        )

    max_to_score = config.get("max_jobs_to_score", 200)
    if len(scoreable_jobs) > max_to_score:
        logger.warning(
            f"Job count ({len(scoreable_jobs)}) exceeds max_jobs_to_score={max_to_score}. "
            f"Truncating. Raise the cap or narrow job_titles to avoid dropping results."
        )
        scoreable_jobs = scoreable_jobs[:max_to_score]
    new_jobs = scoreable_jobs

    # --- Score ---
    logger.info("=" * 60)
    logger.info("STEP 4: Scoring job fit with Claude...")
    logger.info("=" * 60)
    try:
        client = get_anthropic_client()
        scored_jobs = score_jobs_batch(new_jobs, profile, client)
    except Exception as e:
        logger.error(f"Fit scoring failed: {e}")
        errors.append(f"Fit scoring failed: {e}")
        for job in new_jobs:
            job["fit_score"] = 5
            job["fit_notes"] = "Score unavailable"
        scored_jobs = new_jobs

    min_score = config.get("min_fit_score", 5)

    qualifying_jobs = [j for j in scored_jobs if j.get("fit_score", 0) >= min_score]
    below_threshold = [j for j in scored_jobs if j.get("fit_score", 0) < min_score]
    summary["above_threshold"] = len(qualifying_jobs)
    summary["skipped_below_threshold"] = len(below_threshold)

    logger.info(f"Qualifying jobs (score >= {min_score}): {len(qualifying_jobs)}")
    logger.info(f"Below threshold: {len(below_threshold)}")

    if dry_run:
        logger.info("")
        logger.info("=" * 60)
        logger.info("DRY RUN - No writes will be performed. Here's what would happen:")
        logger.info("=" * 60)
        for job in sorted(qualifying_jobs, key=lambda j: j.get("fit_score", 0), reverse=True):
            score = job.get("fit_score", "?")
            title = job.get("title", "?")
            company = job.get("company", "?")
            search = job.get("search_type", "?")
            logger.info(f"  [{score}/10] {title} @ {company} [{search}]")
        logger.info(f"\nWould add {len(qualifying_jobs)} rows to Google Sheets")
        return summary

    # --- Google Sheets ---
    logger.info("=" * 60)
    logger.info("STEP 5: Updating Google Sheets...")
    logger.info("=" * 60)

    sheets = None
    try:
        sheets = get_sheets_updater(config)
    except Exception as e:
        logger.error(f"Google Sheets connection failed: {e}")
        errors.append(f"Sheets connection failed: {e}")

    # Mark scored jobs AND domain-filtered jobs as seen.
    # Cap-truncated jobs are intentionally left unseen (retry on lower-volume days).
    seen = mark_jobs_seen(new_jobs + domain_skipped, seen)

    # Write below-threshold jobs
    if sheets and below_threshold:
        logger.info(f"Writing {len(below_threshold)} below-threshold jobs to '{BELOW_SHEET}' tab...")
        try:
            sheets.add_jobs_below_threshold_batch(below_threshold)
        except Exception as e:
            logger.error(f"Failed to batch-write below-threshold jobs: {e}")

    for job in qualifying_jobs:
        title = job.get("title", "?")
        company = job.get("company", "?")
        score = job.get("fit_score", "?")
        logger.info(f"Processing [{score}/10]: {title} @ {company}")
        if sheets:
            try:
                sheets.add_job(job)
            except Exception as e:
                logger.error(f"Failed to add job to sheets: {e}")
                errors.append(f"Sheets insert failed for {title} @ {company}: {e}")

    # --- Save seen jobs ---
    try:
        save_seen_jobs(seen, seen_jobs_path)
    except Exception as e:
        logger.error(f"Failed to save seen_jobs.json: {e}")
        errors.append(f"Failed to save seen_jobs.json: {e}")

    # --- Send email ---
    logger.info("=" * 60)
    logger.info("STEP 6: Sending email digest...")
    logger.info("=" * 60)
    try:
        sent = send_digest_from_env(
            new_jobs=qualifying_jobs,
            skipped_count=len(below_threshold),
            duplicate_count=len(duplicates),
            errors=errors,
        )
        if sent:
            logger.info("Email digest sent successfully")
        else:
            logger.warning("Email digest not sent (check email config)")
    except Exception as e:
        logger.error(f"Email notification failed: {e}")
        errors.append(f"Email failed: {e}")

    return summary


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Job Search Automation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py              # Full run
  python main.py --dry-run    # Preview mode - no writes

On a dry run, the tool will:
  - Scrape jobs from all configured boards
  - Score job fit using Claude
  - Print what would be written to Sheets
  - NOT write to Sheets, NOT send email
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in preview mode: scrape + score only, no writes",
    )
    parser.add_argument(
        "--no-age-filter",
        action="store_true",
        help="First-run mode: scrape ALL open positions regardless of post date",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config.yaml"),
        help="Path to config.yaml (default: config.yaml in project root)",
    )
    parser.add_argument(
        "--env",
        default=str(PROJECT_ROOT / ".env"),
        help="Path to .env file (default: .env in project root)",
    )
    args = parser.parse_args()

    load_env(args.env)
    config = load_config(args.config)

    log_dir = str(PROJECT_ROOT / config.get("log_dir", "logs"))
    log_level = config.get("log_level", "INFO")
    setup_logging(log_dir, log_level)

    logger.info("=" * 60)
    logger.info("Job Search Automation Tool - Starting")
    if args.dry_run:
        logger.info("*** DRY RUN MODE - No writes ***")
    if args.no_age_filter:
        logger.info("*** NO AGE FILTER - All open positions ***")
    logger.info("=" * 60)

    try:
        summary = run_pipeline(config, dry_run=args.dry_run, no_age_filter=args.no_age_filter)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Unhandled error in pipeline: {e}")
        sys.exit(1)

    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Scraped:         {summary.get('scraped', 0)}")
    logger.info(f"  New (unseen):    {summary.get('new', 0)}")
    logger.info(f"  Duplicates:      {summary.get('duplicates', 0)}")
    logger.info(f"  Added to sheet:  {summary.get('above_threshold', 0)}")
    logger.info(f"  Below threshold: {summary.get('skipped_below_threshold', 0)}")
    if summary.get("errors"):
        logger.info(f"  Errors:          {len(summary['errors'])}")
        for err in summary["errors"]:
            logger.info(f"    - {err}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
