"""
job_scraper.py

Scrapes job listings using JobSpy across LinkedIn, Indeed, Glassdoor,
and Google Jobs. Runs two separate searches:
  1. National Remote — US-wide, remote-only
  2. Local QC — Quad Cities, IA area, in-person/hybrid acceptable
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from src.ats_scraper import fetch_watchlist_jobs

logger = logging.getLogger(__name__)

SEARCH_TYPE_NATIONAL = "national_remote"
SEARCH_TYPE_LOCAL = "local_qc"
SEARCH_TYPE_WATCHLIST = "watchlist"


def _scrape_for_title(
    title: str,
    job_boards: list[str],
    results_wanted: int,
    country: str,
    is_remote: bool = False,
    location: str = "",
    distance: int = 50,
    employment_types: list[str] | None = None,
) -> list[dict]:
    """
    Run a single JobSpy search for one title.
    Returns a list of normalized job dicts.
    Errors from individual boards are caught so one failure doesn't kill the run.
    """
    try:
        from jobspy import scrape_jobs
    except ImportError:
        raise ImportError("python-jobspy is required: pip install python-jobspy")

    # JobSpy site names
    site_map = {
        "linkedin": "linkedin",
        "indeed": "indeed",
        "glassdoor": "glassdoor",
        "google": "google",
        "zip_recruiter": "zip_recruiter",
    }
    sites = [site_map[b] for b in job_boards if b in site_map]

    job_type = None
    if employment_types:
        # JobSpy accepts a single job_type; use "fulltime" if present, else first
        if "fulltime" in employment_types:
            job_type = "fulltime"
        else:
            job_type = employment_types[0]

    kwargs: dict[str, Any] = {
        "site_name": sites,
        "search_term": title,
        "results_wanted": results_wanted,
        "country_indeed": country,
    }
    if is_remote:
        kwargs["is_remote"] = True
    if location:
        kwargs["location"] = location
        kwargs["distance"] = distance
    if job_type:
        kwargs["job_type"] = job_type

    try:
        df = scrape_jobs(**kwargs)
    except Exception as e:
        logger.error(f"JobSpy scrape failed for '{title}': {e}")
        return []

    if df is None or df.empty:
        logger.info(f"No results for '{title}'")
        return []

    jobs = []
    for _, row in df.iterrows():
        job = {
            "title": str(row.get("title", "") or ""),
            "company": str(row.get("company", "") or ""),
            "location": str(row.get("location", "") or ""),
            "description": str(row.get("description", "") or ""),
            "url": str(row.get("job_url", "") or ""),
            "job_type": str(row.get("job_type", "") or ""),
            "salary_min": row.get("min_amount", None),
            "salary_max": row.get("max_amount", None),
            "salary_currency": str(row.get("currency", "") or "USD"),
            "salary_interval": str(row.get("interval", "") or ""),
            "date_posted": row.get("date_posted", None),
            "is_remote": bool(row.get("is_remote", False)),
            "source": str(row.get("site", "") or ""),
            "search_query": title,
        }
        # Normalize date_posted to a date string
        if job["date_posted"] is not None:
            try:
                if hasattr(job["date_posted"], "isoformat"):
                    job["date_posted"] = job["date_posted"].isoformat()
                else:
                    job["date_posted"] = str(job["date_posted"])
            except Exception:
                job["date_posted"] = ""
        jobs.append(job)

    logger.info(f"  '{title}' -> {len(jobs)} results")
    return jobs


def _is_recent(date_posted_str: str, max_age_hours: int) -> bool:
    """Return True if the job was posted within max_age_hours."""
    if not date_posted_str:
        return True  # Unknown date — include by default

    try:
        # Try ISO format with timezone
        if "T" in date_posted_str:
            dt = datetime.fromisoformat(date_posted_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Date-only string
            dt = datetime.fromisoformat(date_posted_str)
            dt = dt.replace(tzinfo=timezone.utc)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        return dt >= cutoff
    except (ValueError, TypeError):
        return True  # Can't parse — include by default


def _apply_keyword_filters(jobs: list[dict], config: dict, skip_required: bool = False) -> list[dict]:
    """Filter jobs by required and excluded keywords from config."""
    required = [] if skip_required else [k.lower() for k in config.get("required_keywords", [])]
    excluded = [k.lower() for k in config.get("exclude_keywords", [])]
    blacklist = [c.lower() for c in config.get("exclude_companies", [])]

    filtered = []
    for job in jobs:
        searchable = (job["title"] + " " + job["description"]).lower()
        company_lower = job["company"].lower()

        # Company blacklist
        if any(bl in company_lower for bl in blacklist):
            logger.debug(f"Skipping blacklisted company: {job['company']}")
            continue

        # Excluded keywords
        if any(kw in searchable for kw in excluded):
            logger.debug(f"Skipping excluded keyword match: {job['title']} @ {job['company']}")
            continue

        # Required keywords (at least one must match, if list is non-empty)
        if required and not any(kw in searchable for kw in required):
            logger.debug(f"Skipping — no required keyword match: {job['title']} @ {job['company']}")
            continue

        filtered.append(job)

    return filtered


def scrape_national_remote(config: dict) -> list[dict]:
    """
    Search 1: National remote jobs across the US.
    Returns list of job dicts tagged with search_type='national_remote'.
    """
    cfg = config.get("national_remote", {})
    if not cfg.get("enabled", True):
        logger.info("National remote search is disabled in config")
        return []

    titles = config.get("job_titles", [])
    job_boards = cfg.get("job_boards", ["linkedin", "indeed", "glassdoor"])
    results_per = cfg.get("results_per_search", 20)
    max_age = cfg.get("max_age_hours", 24)
    employment_types = cfg.get("employment_types", ["fulltime"])
    country = cfg.get("country", "USA")

    all_jobs = []
    for title in titles:
        logger.info(f"[National Remote] Scraping: {title}")
        jobs = _scrape_for_title(
            title=title,
            job_boards=job_boards,
            results_wanted=results_per,
            country=country,
            is_remote=True,
            employment_types=employment_types,
        )
        # We already asked JobSpy for is_remote=True — trust the board's filter.
        # Don't double-filter by location; some remote jobs have empty/missing location fields.
        jobs = [j for j in jobs if _is_recent(j["date_posted"], max_age)]
        all_jobs.extend(jobs)
        time.sleep(1)  # Be polite to job boards

    all_jobs = _apply_keyword_filters(all_jobs, config)

    for job in all_jobs:
        job["search_type"] = SEARCH_TYPE_NATIONAL

    logger.info(f"[National Remote] Total after filtering: {len(all_jobs)} jobs")
    return all_jobs


def scrape_local_qc(config: dict) -> list[dict]:
    """
    Search 2: Local Quad Cities, IA jobs (in-person or hybrid).
    Returns list of job dicts tagged with search_type='local_qc'.
    """
    cfg = config.get("local_qc", {})
    if not cfg.get("enabled", True):
        logger.info("Local QC search is disabled in config")
        return []

    titles = config.get("job_titles", [])
    job_boards = cfg.get("job_boards", ["linkedin", "indeed", "glassdoor"])
    results_per = cfg.get("results_per_search", 15)
    max_age = cfg.get("max_age_hours", 24)
    employment_types = cfg.get("employment_types", ["fulltime"])
    location = cfg.get("location", "Quad Cities, IA")
    radius = cfg.get("radius_miles", 50)
    country = cfg.get("country", "USA")

    all_jobs = []
    for title in titles:
        logger.info(f"[Local QC] Scraping: {title} near {location}")
        jobs = _scrape_for_title(
            title=title,
            job_boards=job_boards,
            results_wanted=results_per,
            country=country,
            location=location,
            distance=radius,
            employment_types=employment_types,
        )
        jobs = [j for j in jobs if _is_recent(j["date_posted"], max_age)]
        all_jobs.extend(jobs)
        time.sleep(1)

    # Skip required_keywords for local search — local postings use generic titles
    # and won't contain "digital delivery" etc. Excluded keywords still apply.
    all_jobs = _apply_keyword_filters(all_jobs, config, skip_required=True)

    for job in all_jobs:
        job["search_type"] = SEARCH_TYPE_LOCAL

    logger.info(f"[Local QC] Total after filtering: {len(all_jobs)} jobs")
    return all_jobs


def scrape_watchlist(config: dict) -> list[dict]:
    """
    Fetch jobs from company ATS endpoints via the Watchlist Google Sheet tab.
    Returns list of job dicts tagged with search_type='watchlist'.
    Required keywords are skipped (watchlist jobs aren't found by title query).
    """
    cfg = config.get("watchlist", {})
    if not cfg.get("enabled", True):
        logger.info("Watchlist scan is disabled in config")
        return []

    jobs = fetch_watchlist_jobs(config)
    jobs = _apply_keyword_filters(jobs, config, skip_required=True)

    for job in jobs:
        job["search_type"] = SEARCH_TYPE_WATCHLIST

    logger.info(f"[Watchlist] Total after filtering: {len(jobs)} jobs")
    return jobs


def scrape_all_jobs(config: dict) -> list[dict]:
    """
    Run all three searches and return combined results.
    Each job has a 'search_type' field to distinguish them.
    """
    national = scrape_national_remote(config)
    local = scrape_local_qc(config)
    watchlist = scrape_watchlist(config)
    combined = national + local + watchlist
    logger.info(
        f"Total jobs scraped: {len(combined)} "
        f"({len(national)} national, {len(local)} local, {len(watchlist)} watchlist)"
    )
    return combined


def format_salary(job: dict) -> str:
    """Format salary range as a human-readable string."""
    s_min = job.get("salary_min")
    s_max = job.get("salary_max")
    interval = job.get("salary_interval", "")
    currency = job.get("salary_currency", "USD")

    if s_min is None and s_max is None:
        return ""

    def fmt(val):
        if val is None:
            return ""
        try:
            n = int(float(val))
            if n >= 1000:
                return f"${n:,}"
            return f"${n}"
        except (ValueError, TypeError):
            return str(val)

    parts = [p for p in [fmt(s_min), fmt(s_max)] if p]
    result = " – ".join(parts)
    if interval and interval.lower() not in ("", "yearly", "annual", "year"):
        result += f"/{interval}"
    return result
