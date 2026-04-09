# tests/test_ats_scraper.py
"""Unit tests for src/ats_scraper.py"""

def test_search_type_label_exists():
    """The 'watchlist' search_type must have a display label."""
    from src.sheets_updater import SEARCH_TYPE_LABELS
    assert "watchlist" in SEARCH_TYPE_LABELS
    assert SEARCH_TYPE_LABELS["watchlist"] == "ATS Watchlist"

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

def test_slug_candidates_empty_name():
    from src.ats_scraper import _generate_slug_candidates
    # Names that produce no valid slug return empty list
    assert _generate_slug_candidates("!!!") == []

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
    # Must have all 14 standard fields
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


def test_normalize_produces_exactly_14_fields():
    """Normalizers must produce exactly the 14 standard fields — no more, no less."""
    from src.ats_scraper import _normalize_greenhouse
    raw = {"title": "Test", "location": {"name": "Remote"}, "absolute_url": "", "content": "", "updated_at": None}
    job = _normalize_greenhouse(raw, "TestCo")
    standard_fields = {"title", "company", "location", "description", "url", "job_type",
                       "salary_min", "salary_max", "salary_currency", "salary_interval",
                       "date_posted", "is_remote", "source", "search_query"}
    assert set(job.keys()) == standard_fields
