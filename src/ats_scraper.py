"""
ats_scraper.py

Fetches jobs directly from company ATS (Applicant Tracking System) endpoints.
Supports: Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, BambooHR.

Companies are read from the "Watchlist" tab in Google Sheets. Unknown companies
are auto-detected (ATS type + slug probed and cached back to the sheet).
"""

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

WATCHLIST_SHEET = "Watchlist"
WATCHLIST_HEADERS = ["Company Name", "ATS Type", "Slug", "Status", "Date Added", "Last Scanned"]

PROBE_DELAY = 0.2   # seconds between ATS probe requests
REQUEST_TIMEOUT = 10  # seconds per HTTP request

_STRIP_SUFFIXES = [
    ", inc.", ", llc", ", corp.", ", ltd.", ", co.",
    " inc", " llc", " corp", " ltd", " co",
    " agency", " digital", " group", " media", " marketing",
    " communications", " interactive", " creative", " solutions",
]


def _generate_slug_candidates(company_name: str) -> list[str]:
    """Generate likely ATS slug candidates from a company name."""
    name = company_name.lower().strip()
    for suffix in _STRIP_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    slug = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    if not slug:
        return []
    candidates = [slug]
    no_hyphens = slug.replace("-", "")
    if no_hyphens != slug:
        candidates.append(no_hyphens)
    return list(dict.fromkeys(candidates))


def _parse_date(value) -> datetime | None:
    """Parse a date value (ISO string or Unix ms int) into a UTC datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            ts = value / 1000 if value > 1e10 else value
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_within_days(value: str | int | float | None, days: int) -> bool:
    """Return True if value parses to a date within the last N days. Unknown dates return True."""
    dt = _parse_date(value)
    if dt is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return dt >= cutoff


# ─────────────────────────────────────────────────────────────
# HTTP helper
# ─────────────────────────────────────────────────────────────

def _get(url: str) -> dict | list | None:
    """GET request returning parsed JSON, or None on any error."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "JobSearchBot/1.0"})
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# ATS Fetch Functions
# ─────────────────────────────────────────────────────────────

def fetch_greenhouse(slug: str) -> list[dict] | None:
    """Returns list of raw job dicts, or None if endpoint unreachable."""
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    if data is None:
        return None
    jobs = data.get("jobs")
    return jobs if isinstance(jobs, list) else None


def fetch_lever(slug: str) -> list[dict] | None:
    data = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    return data if isinstance(data, list) else None


def fetch_ashby(slug: str) -> list[dict] | None:
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if data is None:
        return None
    jobs = data.get("jobPostings")
    return jobs if isinstance(jobs, list) else None


def fetch_smartrecruiters(slug: str) -> list[dict] | None:
    data = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings")
    if data is None:
        return None
    jobs = data.get("content")
    return jobs if isinstance(jobs, list) else None


def fetch_recruitee(slug: str) -> list[dict] | None:
    data = _get(f"https://{slug}.recruitee.com/api/offers/")
    if data is None:
        return None
    jobs = data.get("offers")
    return jobs if isinstance(jobs, list) else None


def fetch_bamboohr(slug: str) -> list[dict] | None:
    data = _get(f"https://{slug}.bamboohr.com/careers/list")
    if data is None:
        return None
    if isinstance(data, list):
        return data
    for key in ("result", "jobs", "positions"):
        if isinstance(data.get(key), list):
            return data[key]
    return None


ATS_ADAPTERS: dict[str, callable] = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
    "recruitee": fetch_recruitee,
    "bamboohr": fetch_bamboohr,
}


# ─────────────────────────────────────────────────────────────
# Remote Detection (one function per ATS)
# ─────────────────────────────────────────────────────────────

def _is_remote_greenhouse(job: dict) -> bool:
    loc = job.get("location", {})
    name = loc.get("name", "") if isinstance(loc, dict) else str(loc)
    return "remote" in name.lower()


def _is_remote_lever(job: dict) -> bool:
    cats = job.get("categories", {})
    location = cats.get("location", "").lower() if isinstance(cats, dict) else ""
    workplace = job.get("workplaceType", "").lower()
    return "remote" in location or workplace == "remote"


def _is_remote_ashby(job: dict) -> bool:
    if job.get("isRemote"):
        return True
    loc = job.get("location", "")
    name = loc.get("name", "") if isinstance(loc, dict) else str(loc)
    return "remote" in name.lower()


def _is_remote_smartrecruiters(job: dict) -> bool:
    loc = job.get("location", {})
    if isinstance(loc, dict):
        if loc.get("remote"):
            return True
        return "remote" in loc.get("city", "").lower()
    return "remote" in str(loc).lower()


def _is_remote_recruitee(job: dict) -> bool:
    if job.get("remote"):
        return True
    return "remote" in job.get("city_text", "").lower()


def _is_remote_bamboohr(job: dict) -> bool:
    loc = job.get("location", {})
    city = loc.get("city", "") if isinstance(loc, dict) else str(loc)
    return "remote" in city.lower()


REMOTE_DETECTORS: dict[str, callable] = {
    "greenhouse": _is_remote_greenhouse,
    "lever": _is_remote_lever,
    "ashby": _is_remote_ashby,
    "smartrecruiters": _is_remote_smartrecruiters,
    "recruitee": _is_remote_recruitee,
    "bamboohr": _is_remote_bamboohr,
}


# ─────────────────────────────────────────────────────────────
# Date Extraction (one function per ATS)
# ─────────────────────────────────────────────────────────────

def _get_date_greenhouse(job: dict):
    return job.get("updated_at") or job.get("created_at")

def _get_date_lever(job: dict):
    return job.get("createdAt")           # Unix ms integer

def _get_date_ashby(job: dict):
    return job.get("publishedDate")

def _get_date_smartrecruiters(job: dict):
    return job.get("createDate")

def _get_date_recruitee(job: dict):
    return job.get("created_at")

def _get_date_bamboohr(job: dict):
    return job.get("datePosted") or job.get("created_at")


DATE_EXTRACTORS: dict[str, callable] = {
    "greenhouse": _get_date_greenhouse,
    "lever": _get_date_lever,
    "ashby": _get_date_ashby,
    "smartrecruiters": _get_date_smartrecruiters,
    "recruitee": _get_date_recruitee,
    "bamboohr": _get_date_bamboohr,
}


# ─────────────────────────────────────────────────────────────
# Job Normalization (one function per ATS → standard 14-field job dict)
# ─────────────────────────────────────────────────────────────

def _make_job(title, company, location, description, url, date_val, is_remote, source) -> dict:
    """Build a standard job dict. All ATS normalizers call this."""
    dt = _parse_date(date_val)
    return {
        "title": str(title or ""),
        "company": str(company or ""),
        "location": str(location or ""),
        "description": str(description or ""),
        "url": str(url or ""),
        "job_type": "fulltime",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "USD",
        "salary_interval": "",
        "date_posted": dt.isoformat() if dt else "",
        "is_remote": bool(is_remote),
        "source": source,
        "search_query": company,
    }


def _normalize_greenhouse(job: dict, company_name: str) -> dict:
    loc = job.get("location", {})
    loc_str = loc.get("name", "") if isinstance(loc, dict) else str(loc)
    return _make_job(
        title=job.get("title"),
        company=company_name,
        location=loc_str,
        description=job.get("content", ""),
        url=job.get("absolute_url", ""),
        date_val=_get_date_greenhouse(job),
        is_remote=_is_remote_greenhouse(job),
        source="greenhouse",
    )


def _normalize_lever(job: dict, company_name: str) -> dict:
    cats = job.get("categories", {}) if isinstance(job.get("categories"), dict) else {}
    return _make_job(
        title=job.get("text"),
        company=company_name,
        location=cats.get("location", ""),
        description=job.get("descriptionPlain", "") or job.get("description", ""),
        url=job.get("hostedUrl", ""),
        date_val=_get_date_lever(job),
        is_remote=_is_remote_lever(job),
        source="lever",
    )


def _normalize_ashby(job: dict, company_name: str) -> dict:
    loc = job.get("location", "")
    loc_str = loc.get("name", "") if isinstance(loc, dict) else str(loc)
    return _make_job(
        title=job.get("title"),
        company=company_name,
        location=loc_str,
        description=job.get("descriptionHtml", "") or job.get("descriptionPlain", ""),
        url=job.get("jobUrl", "") or job.get("applyUrl", ""),
        date_val=_get_date_ashby(job),
        is_remote=_is_remote_ashby(job),
        source="ashby",
    )


def _normalize_smartrecruiters(job: dict, company_name: str) -> dict:
    loc = job.get("location", {})
    if isinstance(loc, dict):
        parts = [loc.get("city", ""), loc.get("country", "")]
        loc_str = ", ".join(p for p in parts if p)
    else:
        loc_str = str(loc)
    job_id = job.get("id", "")
    url = f"https://jobs.smartrecruiters.com/{company_name.replace(' ', '')}/{job_id}" if job_id else ""
    return _make_job(
        title=job.get("name"),
        company=company_name,
        location=loc_str,
        description=job.get("jobAdText", ""),
        url=url,
        date_val=_get_date_smartrecruiters(job),
        is_remote=_is_remote_smartrecruiters(job),
        source="smartrecruiters",
    )


def _normalize_recruitee(job: dict, company_name: str) -> dict:
    return _make_job(
        title=job.get("title"),
        company=company_name,
        location=job.get("city_text", "") or job.get("location", ""),
        description=job.get("description", ""),
        url=job.get("careers_url", ""),
        date_val=_get_date_recruitee(job),
        is_remote=_is_remote_recruitee(job),
        source="recruitee",
    )


def _normalize_bamboohr(job: dict, company_name: str) -> dict:
    loc = job.get("location", {})
    loc_str = loc.get("city", "") if isinstance(loc, dict) else str(loc)
    title_field = job.get("title", {})
    title = title_field.get("label", "") if isinstance(title_field, dict) else str(title_field)
    job_id = job.get("id", "")
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
    url = f"https://{slug}.bamboohr.com/careers/{job_id}" if job_id else ""
    return _make_job(
        title=title,
        company=company_name,
        location=loc_str,
        description=job.get("description", ""),
        url=url,
        date_val=_get_date_bamboohr(job),
        is_remote=_is_remote_bamboohr(job),
        source="bamboohr",
    )


NORMALIZERS: dict[str, callable] = {
    "greenhouse": _normalize_greenhouse,
    "lever": _normalize_lever,
    "ashby": _normalize_ashby,
    "smartrecruiters": _normalize_smartrecruiters,
    "recruitee": _normalize_recruitee,
    "bamboohr": _normalize_bamboohr,
}


# ─────────────────────────────────────────────────────────────
# ATS Auto-Detection
# ─────────────────────────────────────────────────────────────

def detect_ats(company_name: str, detection_order: list[str]) -> tuple[str, str] | tuple[None, None]:
    """Probe ATS endpoints to find which one hosts this company's jobs.

    Returns (ats_type, slug) on first successful probe, or (None, None) if all fail.
    A successful probe means the endpoint returned a valid response (even an empty job list).
    """
    candidates = _generate_slug_candidates(company_name)
    if not candidates:
        return None, None
    for ats in detection_order:
        fetch_fn = ATS_ADAPTERS.get(ats)
        if not fetch_fn:
            continue
        for slug in candidates:
            try:
                result = fetch_fn(slug)
                if result is not None:   # None = network/parse error; [] = valid but no current jobs
                    logger.info(f"  Detected {company_name} → {ats}/{slug}")
                    return ats, slug
            except Exception:
                pass
            time.sleep(PROBE_DELAY)
    logger.info(f"  No ATS detected for: {company_name}")
    return None, None
