# ATS Watchlist Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily "watchlist" scan that fetches jobs directly from company ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, BambooHR), auto-detects which ATS each company uses, and feeds results through the existing dedup → score → sheets → email pipeline unchanged.

**Architecture:** A new `src/ats_scraper.py` module handles all ATS adapter logic, slug auto-detection, and Google Sheets watchlist tab read/write. A new `scrape_watchlist()` function in `job_scraper.py` calls into it and returns normalized job dicts tagged `search_type="watchlist"`. `scrape_all_jobs()` gains one line. Everything downstream is untouched.

**Tech Stack:** Python 3.11+, `requests`, `gspread`, `google-auth` (all already installed). No new dependencies.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/ats_scraper.py` | **Create** | All ATS adapter logic, slug generation, auto-detection, GSheets watchlist read/write, job normalization |
| `tests/test_ats_scraper.py` | **Create** | Unit tests for all pure functions + mocked HTTP/GSheets |
| `src/job_scraper.py` | **Modify** | Add `scrape_watchlist()` (lines 258–278), modify `scrape_all_jobs()` (lines 258–267 become 258–270) |
| `src/sheets_updater.py` | **Modify** | Add `"watchlist": "ATS Watchlist"` to `SEARCH_TYPE_LABELS` (line 65) |
| `config.yaml` | **Modify** | Add `watchlist:` section after `local_qc:` block |

---

## Task 1: Config + Label Changes

**Files:**
- Modify: `config.yaml` (after line 234)
- Modify: `src/sheets_updater.py:62-65`
- Test: `tests/test_ats_scraper.py` (create file, first test)

- [ ] **Step 1: Create test file with first test**

```python
# tests/test_ats_scraper.py
"""Unit tests for src/ats_scraper.py"""

def test_search_type_label_exists():
    """The 'watchlist' search_type must have a display label."""
    from src.sheets_updater import SEARCH_TYPE_LABELS
    assert "watchlist" in SEARCH_TYPE_LABELS
    assert SEARCH_TYPE_LABELS["watchlist"] == "ATS Watchlist"
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_ats_scraper.py::test_search_type_label_exists -v
```
Expected: FAIL — `AssertionError` (key not in dict)

- [ ] **Step 3: Add label to sheets_updater.py**

In `src/sheets_updater.py`, change lines 62–65 from:
```python
SEARCH_TYPE_LABELS = {
    "national_remote": "National Remote",
    "local_qc": "Local QC",
}
```
to:
```python
SEARCH_TYPE_LABELS = {
    "national_remote": "National Remote",
    "local_qc": "Local QC",
    "watchlist": "ATS Watchlist",
}
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m pytest tests/test_ats_scraper.py::test_search_type_label_exists -v
```
Expected: PASS

- [ ] **Step 5: Add watchlist section to config.yaml**

Add after the `local_qc:` block (after line 234):

```yaml
# ---- ATS Watchlist Scan Config ---------------------------
# Companies are managed in the "Watchlist" tab of your Google Sheet.
# Add a company name to that tab and the tool auto-detects its ATS on the next run.
watchlist:
  enabled: true
  # Only fetch jobs posted/updated within this many days (avoids reprocessing old postings)
  lookback_days: 3
  # ATS probe order for unknown companies (first successful match wins)
  detection_order:
    - greenhouse
    - lever
    - ashby
    - smartrecruiters
    - recruitee
    - bamboohr
```

- [ ] **Step 6: Commit**

```bash
git add src/sheets_updater.py config.yaml tests/test_ats_scraper.py
git commit -m "config: add watchlist section and ATS Watchlist search type label"
```

---

## Task 2: Core Utilities — Slug Generation + Date Parsing

**Files:**
- Create: `src/ats_scraper.py` (first section)
- Test: `tests/test_ats_scraper.py`

- [ ] **Step 1: Write failing tests for slug generation**

Append to `tests/test_ats_scraper.py`:

```python
def test_slug_candidates_simple():
    from src.ats_scraper import _generate_slug_candidates
    candidates = _generate_slug_candidates("Ogilvy")
    assert "ogilvy" in candidates

def test_slug_candidates_strips_suffix():
    from src.ats_scraper import _generate_slug_candidates
    candidates = _generate_slug_candidates("Huge Agency")
    assert "huge" in candidates

def test_slug_candidates_multi_word():
    from src.ats_scraper import _generate_slug_candidates
    candidates = _generate_slug_candidates("R/GA")
    assert "r-ga" in candidates or "rga" in candidates

def test_slug_candidates_inc_suffix():
    from src.ats_scraper import _generate_slug_candidates
    candidates = _generate_slug_candidates("Merkle, Inc.")
    assert "merkle" in candidates

def test_parse_date_iso():
    from src.ats_scraper import _parse_date
    from datetime import timezone
    dt = _parse_date("2026-01-15T10:30:00Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc

def test_parse_date_unix_ms():
    from src.ats_scraper import _parse_date
    # Lever uses Unix ms timestamps
    dt = _parse_date(1705312200000)
    assert dt is not None
    assert dt.year == 2024

def test_parse_date_none():
    from src.ats_scraper import _parse_date
    assert _parse_date(None) is None

def test_is_within_days_recent():
    from src.ats_scraper import _is_within_days
    from datetime import datetime, timezone, timedelta
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert _is_within_days(recent, 3) is True

def test_is_within_days_old():
    from src.ats_scraper import _is_within_days
    from datetime import datetime, timezone, timedelta
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    assert _is_within_days(old, 3) is False

def test_is_within_days_none():
    from src.ats_scraper import _is_within_days
    # Unknown date → include by default
    assert _is_within_days(None, 3) is True
```

- [ ] **Step 2: Run tests to verify they all fail**

```
python -m pytest tests/test_ats_scraper.py -k "slug or date or within" -v
```
Expected: All FAIL — `ModuleNotFoundError: No module named 'src.ats_scraper'`

- [ ] **Step 3: Create src/ats_scraper.py with core utilities**

```python
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


def _is_within_days(value, days: int) -> bool:
    """Return True if value parses to a date within the last N days. Unknown dates return True."""
    dt = _parse_date(value)
    if dt is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return dt >= cutoff
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_ats_scraper.py -k "slug or date or within" -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ats_scraper.py tests/test_ats_scraper.py
git commit -m "feat: add ats_scraper core utilities (slug generation, date parsing)"
```

---

## Task 3: ATS Fetch Adapters

**Files:**
- Modify: `src/ats_scraper.py` (append fetch functions + `ATS_ADAPTERS` dict)
- Test: `tests/test_ats_scraper.py`

- [ ] **Step 1: Write failing tests for fetch adapters**

Append to `tests/test_ats_scraper.py`:

```python
from unittest.mock import patch, MagicMock


def _mock_get(return_value):
    """Helper: patch requests.get to return a mock with .json() and .status_code."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = return_value
    return patch("src.ats_scraper.requests.get", return_value=mock_resp)


def test_fetch_greenhouse_returns_jobs():
    from src.ats_scraper import fetch_greenhouse
    payload = {"jobs": [{"id": 1, "title": "VP Digital", "location": {"name": "Remote"}}]}
    with _mock_get(payload):
        result = fetch_greenhouse("ogilvy")
    assert len(result) == 1
    assert result[0]["title"] == "VP Digital"


def test_fetch_greenhouse_returns_none_on_error():
    from src.ats_scraper import fetch_greenhouse
    with patch("src.ats_scraper.requests.get", side_effect=Exception("timeout")):
        result = fetch_greenhouse("ogilvy")
    assert result is None


def test_fetch_lever_returns_jobs():
    from src.ats_scraper import fetch_lever
    payload = [{"text": "Director of Marketing", "categories": {"location": "Remote"}}]
    with _mock_get(payload):
        result = fetch_lever("r-ga")
    assert len(result) == 1
    assert result[0]["text"] == "Director of Marketing"


def test_fetch_ashby_returns_jobs():
    from src.ats_scraper import fetch_ashby
    payload = {"jobPostings": [{"title": "Head of Growth", "isRemote": True}]}
    with _mock_get(payload):
        result = fetch_ashby("linear")
    assert len(result) == 1


def test_fetch_smartrecruiters_returns_jobs():
    from src.ats_scraper import fetch_smartrecruiters
    payload = {"content": [{"name": "Digital Strategy Lead", "location": {"remote": True}}]}
    with _mock_get(payload):
        result = fetch_smartrecruiters("merkle")
    assert len(result) == 1


def test_fetch_recruitee_returns_jobs():
    from src.ats_scraper import fetch_recruitee
    payload = {"offers": [{"title": "SEO Manager", "remote": True, "city_text": "Remote"}]}
    with _mock_get(payload):
        result = fetch_recruitee("someagency")
    assert len(result) == 1


def test_fetch_bamboohr_returns_jobs():
    from src.ats_scraper import fetch_bamboohr
    payload = [{"id": 42, "title": {"label": "Content Strategist"}, "location": {"city": "Remote"}}]
    with _mock_get(payload):
        result = fetch_bamboohr("somecompany")
    assert len(result) == 1


def test_ats_adapters_dict_contains_all():
    from src.ats_scraper import ATS_ADAPTERS
    for name in ("greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "bamboohr"):
        assert name in ATS_ADAPTERS
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_ats_scraper.py -k "fetch" -v
```
Expected: All FAIL — `ImportError` (functions not defined yet)

- [ ] **Step 3: Add fetch adapters to src/ats_scraper.py**

Append to `src/ats_scraper.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_ats_scraper.py -k "fetch or adapters" -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ats_scraper.py tests/test_ats_scraper.py
git commit -m "feat: add ATS fetch adapters (greenhouse, lever, ashby, smartrecruiters, recruitee, bamboohr)"
```

---

## Task 4: Remote Detection + Date Extraction + Job Normalization

**Files:**
- Modify: `src/ats_scraper.py` (append remote detectors, date extractors, normalizers)
- Test: `tests/test_ats_scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ats_scraper.py`:

```python
# ── Remote detection ──────────────────────────────────────────

def test_remote_greenhouse_by_location_name():
    from src.ats_scraper import _is_remote_greenhouse
    assert _is_remote_greenhouse({"location": {"name": "Remote - US"}}) is True

def test_remote_greenhouse_not_remote():
    from src.ats_scraper import _is_remote_greenhouse
    assert _is_remote_greenhouse({"location": {"name": "New York, NY"}}) is False

def test_remote_lever_workplace_type():
    from src.ats_scraper import _is_remote_lever
    assert _is_remote_lever({"workplaceType": "remote", "categories": {}}) is True

def test_remote_lever_location_string():
    from src.ats_scraper import _is_remote_lever
    assert _is_remote_lever({"categories": {"location": "Remote"}, "workplaceType": ""}) is True

def test_remote_ashby_flag():
    from src.ats_scraper import _is_remote_ashby
    assert _is_remote_ashby({"isRemote": True}) is True

def test_remote_smartrecruiters_flag():
    from src.ats_scraper import _is_remote_smartrecruiters
    assert _is_remote_smartrecruiters({"location": {"remote": True}}) is True

def test_remote_recruitee_flag():
    from src.ats_scraper import _is_remote_recruitee
    assert _is_remote_recruitee({"remote": True, "city_text": ""}) is True

# ── Normalization ─────────────────────────────────────────────

def test_normalize_greenhouse_fields():
    from src.ats_scraper import _normalize_greenhouse
    raw = {
        "title": "VP of Digital",
        "location": {"name": "Remote"},
        "absolute_url": "https://boards.greenhouse.io/ogilvy/jobs/123",
        "content": "Job description here",
        "updated_at": "2026-04-01T10:00:00Z",
    }
    job = _normalize_greenhouse(raw, "Ogilvy")
    assert job["title"] == "VP of Digital"
    assert job["company"] == "Ogilvy"
    assert job["location"] == "Remote"
    assert job["url"] == "https://boards.greenhouse.io/ogilvy/jobs/123"
    assert job["source"] == "greenhouse"
    assert job["search_query"] == "Ogilvy"
    assert job["is_remote"] is True
    assert "date_posted" in job
    # Must have all 15 standard fields
    for field in ("title", "company", "location", "description", "url", "job_type",
                  "salary_min", "salary_max", "salary_currency", "salary_interval",
                  "date_posted", "is_remote", "source", "search_query"):
        assert field in job, f"Missing field: {field}"


def test_normalize_lever_fields():
    from src.ats_scraper import _normalize_lever
    raw = {
        "text": "Director of Strategy",
        "categories": {"location": "Remote"},
        "hostedUrl": "https://jobs.lever.co/rga/abc",
        "descriptionPlain": "Description",
        "createdAt": 1705312200000,
        "workplaceType": "remote",
    }
    job = _normalize_lever(raw, "R/GA")
    assert job["title"] == "Director of Strategy"
    assert job["company"] == "R/GA"
    assert job["source"] == "lever"
    assert job["is_remote"] is True


def test_normalize_produces_no_extra_fields():
    """Normalizers must not add fields beyond the 14 standard ones + search_type (added later)."""
    from src.ats_scraper import _normalize_greenhouse
    raw = {"title": "Test", "location": {"name": "Remote"}, "absolute_url": "", "content": "", "updated_at": None}
    job = _normalize_greenhouse(raw, "TestCo")
    standard_fields = {"title", "company", "location", "description", "url", "job_type",
                       "salary_min", "salary_max", "salary_currency", "salary_interval",
                       "date_posted", "is_remote", "source", "search_query"}
    assert set(job.keys()) == standard_fields
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_ats_scraper.py -k "remote or normalize" -v
```
Expected: All FAIL — `ImportError`

- [ ] **Step 3: Add remote detectors + date extractors + normalizers to src/ats_scraper.py**

Append to `src/ats_scraper.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_ats_scraper.py -k "remote or normalize" -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ats_scraper.py tests/test_ats_scraper.py
git commit -m "feat: add ATS remote detection, date extraction, and job normalization"
```

---

## Task 5: ATS Auto-Detection

**Files:**
- Modify: `src/ats_scraper.py` (append `detect_ats`)
- Test: `tests/test_ats_scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ats_scraper.py`:

```python
def test_detect_ats_finds_greenhouse():
    from src.ats_scraper import detect_ats
    greenhouse_payload = {"jobs": [{"title": "Test Job", "location": {"name": "Remote"}}]}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = greenhouse_payload
    with patch("src.ats_scraper.requests.get", return_value=mock_resp):
        ats, slug = detect_ats("Ogilvy", ["greenhouse", "lever"])
    assert ats == "greenhouse"
    assert slug == "ogilvy"


def test_detect_ats_falls_through_to_lever():
    from src.ats_scraper import detect_ats
    lever_payload = [{"text": "Test Job", "categories": {}}]

    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        call_count["n"] += 1
        mock = MagicMock()
        if "greenhouse" in url:
            mock.status_code = 404
            mock.json.return_value = {}
        else:
            mock.status_code = 200
            mock.json.return_value = lever_payload
        return mock

    with patch("src.ats_scraper.requests.get", side_effect=fake_get):
        ats, slug = detect_ats("Huge Agency", ["greenhouse", "lever"])
    assert ats == "lever"
    assert slug in ("huge", "huge-agency")


def test_detect_ats_returns_none_when_all_fail():
    from src.ats_scraper import detect_ats
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.json.return_value = {}
    with patch("src.ats_scraper.requests.get", return_value=mock_resp):
        ats, slug = detect_ats("Unknown Company LLC", ["greenhouse", "lever"])
    assert ats is None
    assert slug is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_ats_scraper.py -k "detect_ats" -v
```
Expected: All FAIL — `ImportError`

- [ ] **Step 3: Add detect_ats to src/ats_scraper.py**

Append to `src/ats_scraper.py`:

```python
# ─────────────────────────────────────────────────────────────
# ATS Auto-Detection
# ─────────────────────────────────────────────────────────────

def detect_ats(company_name: str, detection_order: list[str]) -> tuple[str, str] | tuple[None, None]:
    """Probe ATS endpoints to find which one hosts this company's jobs.

    Returns (ats_type, slug) on first successful probe, or (None, None) if all fail.
    A successful probe means the endpoint returned a valid response (even an empty job list).
    """
    candidates = _generate_slug_candidates(company_name)
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_ats_scraper.py -k "detect_ats" -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ats_scraper.py tests/test_ats_scraper.py
git commit -m "feat: add ATS auto-detection with slug candidate probing"
```

---

## Task 6: Google Sheets Watchlist Read/Write

**Files:**
- Modify: `src/ats_scraper.py` (append watchlist sheet functions)
- Test: `tests/test_ats_scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ats_scraper.py`:

```python
def _mock_worksheet(rows: list[dict]):
    """Build a mock gspread worksheet that returns rows from get_all_records()."""
    ws = MagicMock()
    ws.get_all_records.return_value = rows
    return ws


def test_read_watchlist_returns_rows():
    from src.ats_scraper import read_watchlist
    rows = [
        {"Company Name": "Ogilvy", "ATS Type": "greenhouse", "Slug": "ogilvy", "Status": "active", "Date Added": "", "Last Scanned": ""},
        {"Company Name": "Huge", "ATS Type": "unknown", "Slug": "", "Status": "active", "Date Added": "", "Last Scanned": ""},
    ]
    with patch("src.ats_scraper._get_watchlist_worksheet", return_value=_mock_worksheet(rows)):
        result = read_watchlist({})
    assert len(result) == 2
    assert result[0]["Company Name"] == "Ogilvy"


def test_update_watchlist_detection_calls_update():
    from src.ats_scraper import update_watchlist_detection
    ws = MagicMock()
    with patch("src.ats_scraper._get_watchlist_worksheet", return_value=ws):
        update_watchlist_detection({}, row_index=2, ats_type="greenhouse", slug="ogilvy", date_added="2026-04-09T10:00:00+00:00")
    ws.update.assert_called_once()
    call_args = ws.update.call_args
    assert "B2" in str(call_args)


def test_update_watchlist_last_scanned_calls_update():
    from src.ats_scraper import update_watchlist_last_scanned
    ws = MagicMock()
    with patch("src.ats_scraper._get_watchlist_worksheet", return_value=ws):
        update_watchlist_last_scanned({}, row_index=3, last_scanned="2026-04-09T10:00:00+00:00")
    ws.update.assert_called_once()
    call_args = ws.update.call_args
    assert "F3" in str(call_args)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_ats_scraper.py -k "watchlist" -v
```
Expected: All FAIL — `ImportError`

- [ ] **Step 3: Add watchlist sheet functions to src/ats_scraper.py**

Append to `src/ats_scraper.py`:

```python
# ─────────────────────────────────────────────────────────────
# Google Sheets — Watchlist Tab
# Columns: A=Company Name, B=ATS Type, C=Slug, D=Status, E=Date Added, F=Last Scanned
# ─────────────────────────────────────────────────────────────

def _get_watchlist_worksheet(config: dict):
    """Return the Watchlist worksheet, creating it if needed."""
    import gspread
    from google.oauth2.service_account import Credentials

    sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(sa_path, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)

    try:
        return spreadsheet.worksheet(WATCHLIST_SHEET)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=WATCHLIST_SHEET, rows=1000, cols=len(WATCHLIST_HEADERS))
        ws.insert_row(WATCHLIST_HEADERS, index=1)
        logger.info(f"Created '{WATCHLIST_SHEET}' tab in Google Sheets")
        return ws


def read_watchlist(config: dict) -> list[dict]:
    """Read all rows from the Watchlist sheet tab."""
    ws = _get_watchlist_worksheet(config)
    return ws.get_all_records()


def update_watchlist_detection(config: dict, row_index: int, ats_type: str, slug: str, date_added: str) -> None:
    """Write ATS Type, Slug, Status=active, Date Added for a newly detected company.
    row_index is 1-based (row 1 = header, first data row = 2).
    """
    ws = _get_watchlist_worksheet(config)
    ws.update(f"B{row_index}:E{row_index}", [[ats_type, slug, "active", date_added]])


def update_watchlist_last_scanned(config: dict, row_index: int, last_scanned: str) -> None:
    """Update Last Scanned timestamp for a row."""
    ws = _get_watchlist_worksheet(config)
    ws.update(f"F{row_index}", [[last_scanned]])
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_ats_scraper.py -k "watchlist" -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ats_scraper.py tests/test_ats_scraper.py
git commit -m "feat: add watchlist Google Sheets read/write functions"
```

---

## Task 7: fetch_watchlist_jobs() Orchestrator

**Files:**
- Modify: `src/ats_scraper.py` (append main function)
- Test: `tests/test_ats_scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ats_scraper.py`:

```python
def test_fetch_watchlist_jobs_known_company():
    """Known greenhouse company returns normalized remote jobs."""
    from src.ats_scraper import fetch_watchlist_jobs
    from datetime import datetime, timezone, timedelta

    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    rows = [{"Company Name": "Ogilvy", "ATS Type": "greenhouse", "Slug": "ogilvy",
             "Status": "active", "Date Added": "2026-01-01", "Last Scanned": ""}]
    greenhouse_jobs = [
        {"title": "VP Digital", "location": {"name": "Remote"}, "absolute_url": "https://example.com",
         "content": "Description", "updated_at": recent},
        {"title": "Office Manager", "location": {"name": "New York, NY"}, "absolute_url": "https://example2.com",
         "content": "Description", "updated_at": recent},
    ]
    gh_payload = {"jobs": greenhouse_jobs}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = gh_payload

    config = {"watchlist": {"enabled": True, "lookback_days": 3, "detection_order": ["greenhouse"]}}

    with patch("src.ats_scraper._get_watchlist_worksheet", return_value=_mock_worksheet(rows)), \
         patch("src.ats_scraper.requests.get", return_value=mock_resp), \
         patch("src.ats_scraper.update_watchlist_last_scanned"):
        jobs = fetch_watchlist_jobs(config)

    # Only the remote job should come through
    assert len(jobs) == 1
    assert jobs[0]["title"] == "VP Digital"
    assert jobs[0]["company"] == "Ogilvy"
    assert jobs[0]["is_remote"] is True


def test_fetch_watchlist_jobs_skips_paused():
    from src.ats_scraper import fetch_watchlist_jobs
    rows = [{"Company Name": "Paused Co", "ATS Type": "greenhouse", "Slug": "paused-co",
             "Status": "paused", "Date Added": "", "Last Scanned": ""}]
    config = {"watchlist": {"enabled": True, "lookback_days": 3, "detection_order": ["greenhouse"]}}
    with patch("src.ats_scraper._get_watchlist_worksheet", return_value=_mock_worksheet(rows)):
        jobs = fetch_watchlist_jobs(config)
    assert jobs == []


def test_fetch_watchlist_jobs_disabled():
    from src.ats_scraper import fetch_watchlist_jobs
    config = {"watchlist": {"enabled": False}}
    with patch("src.ats_scraper._get_watchlist_worksheet") as mock_ws:
        jobs = fetch_watchlist_jobs(config)
    mock_ws.assert_not_called()
    assert jobs == []


def test_fetch_watchlist_jobs_filters_old_jobs():
    """Jobs older than lookback_days are excluded."""
    from src.ats_scraper import fetch_watchlist_jobs
    from datetime import datetime, timezone, timedelta

    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    rows = [{"Company Name": "Ogilvy", "ATS Type": "greenhouse", "Slug": "ogilvy",
             "Status": "active", "Date Added": "", "Last Scanned": ""}]
    gh_payload = {"jobs": [
        {"title": "VP Digital", "location": {"name": "Remote"}, "absolute_url": "",
         "content": "", "updated_at": old},
    ]}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = gh_payload

    config = {"watchlist": {"enabled": True, "lookback_days": 3, "detection_order": ["greenhouse"]}}
    with patch("src.ats_scraper._get_watchlist_worksheet", return_value=_mock_worksheet(rows)), \
         patch("src.ats_scraper.requests.get", return_value=mock_resp), \
         patch("src.ats_scraper.update_watchlist_last_scanned"):
        jobs = fetch_watchlist_jobs(config)
    assert jobs == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_ats_scraper.py -k "fetch_watchlist_jobs" -v
```
Expected: All FAIL — `ImportError`

- [ ] **Step 3: Add fetch_watchlist_jobs to src/ats_scraper.py**

Append to `src/ats_scraper.py`:

```python
# ─────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────

def fetch_watchlist_jobs(config: dict) -> list[dict]:
    """
    Read companies from the Watchlist Google Sheet tab, auto-detect ATS for unknowns,
    fetch remote jobs posted within lookback_days, and return normalized job dicts.

    Each returned job has the 14 standard fields. The caller (scrape_watchlist in
    job_scraper.py) adds search_type='watchlist' before returning.
    """
    watchlist_cfg = config.get("watchlist", {})
    if not watchlist_cfg.get("enabled", True):
        return []

    lookback_days = watchlist_cfg.get("lookback_days", 3)
    detection_order = watchlist_cfg.get("detection_order", list(ATS_ADAPTERS.keys()))

    companies = read_watchlist(config)
    all_jobs: list[dict] = []
    now_str = datetime.now(timezone.utc).isoformat()

    for i, row in enumerate(companies, start=2):  # row 1 = header
        company_name = row.get("Company Name", "").strip()
        ats_type = row.get("ATS Type", "unknown").strip().lower()
        slug = row.get("Slug", "").strip()
        status = row.get("Status", "active").strip().lower()

        if not company_name:
            continue
        if status == "paused":
            continue

        # Auto-detect ATS for unknown companies
        if ats_type in ("unknown", ""):
            logger.info(f"[Watchlist] Detecting ATS for: {company_name}")
            detected_ats, detected_slug = detect_ats(company_name, detection_order)
            if detected_ats:
                ats_type = detected_ats
                slug = detected_slug
                update_watchlist_detection(config, i, ats_type, slug, now_str)
            else:
                update_watchlist_detection(config, i, "not_detected", "", now_str)
                continue

        if ats_type == "not_detected":
            continue

        fetch_fn = ATS_ADAPTERS.get(ats_type)
        normalizer = NORMALIZERS.get(ats_type)
        if not fetch_fn or not normalizer:
            logger.warning(f"[Watchlist] Unknown ATS type '{ats_type}' for {company_name}")
            continue

        try:
            raw_jobs = fetch_fn(slug)
            if raw_jobs is None:
                logger.warning(f"[Watchlist] Fetch failed: {ats_type}/{slug} ({company_name})")
                continue

            remote_detector = REMOTE_DETECTORS[ats_type]
            date_extractor = DATE_EXTRACTORS[ats_type]
            count_before = len(all_jobs)

            for raw in raw_jobs:
                if not remote_detector(raw):
                    continue
                if not _is_within_days(date_extractor(raw), lookback_days):
                    continue
                all_jobs.append(normalizer(raw, company_name))

            found = len(all_jobs) - count_before
            logger.info(f"[Watchlist] {company_name} ({ats_type}): {found} new remote jobs")
            update_watchlist_last_scanned(config, i, now_str)

        except Exception as e:
            logger.error(f"[Watchlist] Error processing {company_name}: {e}")

        time.sleep(0.1)

    logger.info(f"[Watchlist] Total raw jobs fetched: {len(all_jobs)}")
    return all_jobs
```

- [ ] **Step 4: Run all tests**

```
python -m pytest tests/test_ats_scraper.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ats_scraper.py tests/test_ats_scraper.py
git commit -m "feat: add fetch_watchlist_jobs orchestrator"
```

---

## Task 8: Integration into job_scraper.py

**Files:**
- Modify: `src/job_scraper.py` (add `scrape_watchlist`, modify `scrape_all_jobs`)
- Test: `tests/test_ats_scraper.py`

- [ ] **Step 1: Write failing integration tests**

Append to `tests/test_ats_scraper.py`:

```python
def test_scrape_watchlist_tags_search_type():
    """scrape_watchlist() must tag every job with search_type='watchlist'."""
    from src.job_scraper import scrape_watchlist
    fake_jobs = [
        {"title": "VP Digital", "company": "Ogilvy", "location": "Remote",
         "description": "digital marketing strategy", "url": "https://example.com",
         "job_type": "fulltime", "salary_min": None, "salary_max": None,
         "salary_currency": "USD", "salary_interval": "", "date_posted": "",
         "is_remote": True, "source": "greenhouse", "search_query": "Ogilvy"},
    ]
    config = {
        "watchlist": {"enabled": True, "lookback_days": 3, "detection_order": ["greenhouse"]},
        "required_keywords": [],
        "exclude_keywords": [],
        "exclude_companies": [],
    }
    with patch("src.job_scraper.fetch_watchlist_jobs", return_value=fake_jobs):
        result = scrape_watchlist(config)
    assert len(result) == 1
    assert result[0]["search_type"] == "watchlist"


def test_scrape_watchlist_applies_keyword_filter():
    """Excluded keywords must filter out watchlist jobs."""
    from src.job_scraper import scrape_watchlist
    fake_jobs = [
        {"title": "VP Digital", "company": "Ogilvy", "location": "Remote",
         "description": "staffing agency recruiter placement", "url": "",
         "job_type": "fulltime", "salary_min": None, "salary_max": None,
         "salary_currency": "USD", "salary_interval": "", "date_posted": "",
         "is_remote": True, "source": "greenhouse", "search_query": "Ogilvy"},
    ]
    config = {
        "watchlist": {"enabled": True, "lookback_days": 3, "detection_order": ["greenhouse"]},
        "required_keywords": [],
        "exclude_keywords": ["staffing"],
        "exclude_companies": [],
    }
    with patch("src.job_scraper.fetch_watchlist_jobs", return_value=fake_jobs):
        result = scrape_watchlist(config)
    assert result == []


def test_scrape_all_jobs_includes_watchlist():
    """scrape_all_jobs() must include watchlist results in combined output."""
    from src.job_scraper import scrape_all_jobs
    national_job = {"title": "National Job", "search_type": "national_remote"}
    watchlist_job = {"title": "Watchlist Job", "search_type": "watchlist"}

    config = {
        "watchlist": {"enabled": True, "lookback_days": 3, "detection_order": []},
        "national_remote": {"enabled": False},
        "local_qc": {"enabled": False},
        "required_keywords": [],
        "exclude_keywords": [],
        "exclude_companies": [],
    }
    with patch("src.job_scraper.scrape_national_remote", return_value=[national_job]), \
         patch("src.job_scraper.scrape_local_qc", return_value=[]), \
         patch("src.job_scraper.fetch_watchlist_jobs", return_value=[
             {**watchlist_job, "description": "", "company": "TestCo",
              "location": "", "url": "", "job_type": "", "salary_min": None,
              "salary_max": None, "salary_currency": "USD", "salary_interval": "",
              "date_posted": "", "is_remote": True, "source": "greenhouse",
              "search_query": "TestCo"}
         ]):
        result = scrape_all_jobs(config)
    titles = [j["title"] for j in result]
    assert "National Job" in titles
    assert "Watchlist Job" in titles
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_ats_scraper.py -k "scrape_watchlist or scrape_all_jobs" -v
```
Expected: All FAIL — `ImportError` (function not defined yet)

- [ ] **Step 3: Add scrape_watchlist() to src/job_scraper.py**

Add this import at the top of `src/job_scraper.py` (after existing imports):
```python
from src.ats_scraper import fetch_watchlist_jobs
```

Add this function after line 255 (after `scrape_local_qc`), before `scrape_all_jobs`:

```python
SEARCH_TYPE_WATCHLIST = "watchlist"


def scrape_watchlist(config: dict) -> list[dict]:
    """
    Fetch jobs from company ATS endpoints via the Watchlist Google Sheet tab.
    Returns list of job dicts tagged with search_type='watchlist'.
    """
    cfg = config.get("watchlist", {})
    if not cfg.get("enabled", True):
        logger.info("Watchlist scan is disabled in config")
        return []

    jobs = fetch_watchlist_jobs(config)

    # Apply same keyword filters as other sources (skip required_keywords — watchlist jobs
    # won't use job title queries, so required keyword matching would be too restrictive)
    jobs = _apply_keyword_filters(jobs, config, skip_required=True)

    for job in jobs:
        job["search_type"] = SEARCH_TYPE_WATCHLIST

    logger.info(f"[Watchlist] Total after filtering: {len(jobs)} jobs")
    return jobs
```

- [ ] **Step 4: Modify scrape_all_jobs() in src/job_scraper.py**

Change lines 258–267 from:
```python
def scrape_all_jobs(config: dict) -> list[dict]:
    """
    Run both searches and return combined results.
    Each job has a 'search_type' field to distinguish them.
    """
    national = scrape_national_remote(config)
    local = scrape_local_qc(config)
    combined = national + local
    logger.info(f"Total jobs scraped: {len(combined)} ({len(national)} national, {len(local)} local)")
    return combined
```
to:
```python
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
```

- [ ] **Step 5: Run all tests**

```
python -m pytest tests/test_ats_scraper.py -v
```
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/job_scraper.py tests/test_ats_scraper.py
git commit -m "feat: integrate watchlist scanner into job scraping pipeline"
```

---

## Task 9: End-to-End Verification

**No new code — run the tool against real services.**

- [ ] **Step 1: Create Watchlist sheet tab (if not already created by first run)**

Either run the tool once (it auto-creates the tab) or manually create a tab named **"Watchlist"** in your Google Sheet with these headers in row 1:
```
Company Name | ATS Type | Slug | Status | Date Added | Last Scanned
```

- [ ] **Step 2: Seed with 5 test companies**

Add these rows to the Watchlist tab (ATS Type = "unknown" for all, leave other columns blank):
```
Ogilvy        | unknown | | | |
R/GA          | unknown | | | |
Huge          | unknown | | | |
Merkle        | unknown | | | |
Razorfish     | unknown | | | |
```

- [ ] **Step 3: Run dry run**

```
python main.py --dry-run
```

Expected log output:
```
[Watchlist] Detecting ATS for: Ogilvy
  Detected Ogilvy → greenhouse/ogilvy
[Watchlist] Ogilvy (greenhouse): N new remote jobs
...
[Watchlist] Total after filtering: N jobs
Total jobs scraped: N (X national, Y local, Z watchlist)
```

Check that Watchlist tab is updated: ATS Type and Slug columns populated, Date Added set.

- [ ] **Step 4: Verify deduplication works**

If any watchlist company also posts on LinkedIn/Indeed, run with a company that does. The log should show the second occurrence as a duplicate:
```
Duplicates skipped: N
```
Google Sheet should only have one row per job.

- [ ] **Step 5: Verify full run writes to Google Sheets**

```
python main.py
```

Check Google Sheet "Jobs" tab: any qualifying watchlist jobs should appear with **"ATS Watchlist"** in the Search Type column.

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: ATS watchlist scanner — daily direct-from-ATS job scanning

Adds a new 'watchlist' job source that fetches jobs directly from company
ATS endpoints (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, BambooHR).
Companies are managed via a Google Sheet 'Watchlist' tab. ATS type and slug
are auto-detected on first encounter and cached. Results flow through the
existing dedup → score → sheets → email pipeline unchanged.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ 6 ATS adapters implemented (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, BambooHR)
- ✅ Auto-detection with slug candidates (handles Inc/LLC/Agency suffixes)
- ✅ Remote filtering per-ATS (different field names per platform)
- ✅ Date/recency filtering (lookback_days config)
- ✅ Google Sheets watchlist tab read/write (detection cache + last scanned)
- ✅ Normalized to standard 14-field job dict
- ✅ search_type="watchlist" for sheets label
- ✅ Integrated into scrape_all_jobs() — dedup/score/sheets/email unchanged
- ✅ Paused status respected
- ✅ Disabled config flag respected
- ✅ skip_required=True for keyword filter (same as local_qc — watchlist doesn't use title queries)

**No placeholders:** Every step has actual code.

**Type consistency:** `fetch_watchlist_jobs` is imported in `job_scraper.py` and called in `scrape_watchlist()`. `ATS_ADAPTERS`, `REMOTE_DETECTORS`, `NORMALIZERS`, `DATE_EXTRACTORS` all use the same keys. `_make_job()` is the single source of truth for job dict structure.
