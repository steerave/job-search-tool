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


# ── Google Sheets Watchlist ───────────────────────────────────

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


def test_fetch_watchlist_jobs_known_company():
    """Known greenhouse company returns normalized remote jobs only."""
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
    config = {
        "watchlist": {"enabled": True, "lookback_days": 3, "detection_order": []},
        "national_remote": {"enabled": False},
        "local_qc": {"enabled": False},
        "required_keywords": [],
        "exclude_keywords": [],
        "exclude_companies": [],
    }
    watchlist_job = {
        "title": "Watchlist Job", "company": "TestCo", "location": "Remote",
        "description": "", "url": "", "job_type": "fulltime",
        "salary_min": None, "salary_max": None, "salary_currency": "USD",
        "salary_interval": "", "date_posted": "", "is_remote": True,
        "source": "greenhouse", "search_query": "TestCo",
    }
    with patch("src.job_scraper.scrape_national_remote", return_value=[]), \
         patch("src.job_scraper.scrape_local_qc", return_value=[]), \
         patch("src.job_scraper.fetch_watchlist_jobs", return_value=[watchlist_job]):
        result = scrape_all_jobs(config)
    assert any(j["search_type"] == "watchlist" for j in result)
    assert any(j["title"] == "Watchlist Job" for j in result)


# ── Parallel scanning ─────────────────────────────────────────

def test_scan_company_returns_jobs_and_update():
    """_scan_company returns remote jobs and a Last Scanned update for a known company."""
    from src.ats_scraper import _scan_company
    from datetime import datetime, timezone, timedelta

    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    row = {
        "Company Name": "Ogilvy",
        "ATS Type": "greenhouse",
        "Slug": "ogilvy",
        "Status": "active",
        "Date Added": "",
        "Last Scanned": "",
    }
    gh_payload = {"jobs": [
        {"title": "VP Digital", "location": {"name": "Remote"},
         "absolute_url": "https://example.com", "content": "desc", "updated_at": recent},
        {"title": "Office Manager", "location": {"name": "New York, NY"},
         "absolute_url": "https://example2.com", "content": "desc", "updated_at": recent},
    ]}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = gh_payload

    now_str = datetime.now(timezone.utc).isoformat()

    with patch("src.ats_scraper.requests.get", return_value=mock_resp):
        jobs, updates = _scan_company(row, 2, lookback_days=3,
                                      detection_order=["greenhouse"], now_str=now_str)

    # Only remote job returned
    assert len(jobs) == 1
    assert jobs[0]["title"] == "VP Digital"
    # Last Scanned update queued
    assert len(updates) == 1
    assert updates[0]["range"] == "F2"
    assert updates[0]["values"] == [[now_str]]


def test_scan_company_returns_empty_on_fetch_failure():
    """_scan_company returns ([], []) when the ATS fetch fails — no exception raised."""
    from src.ats_scraper import _scan_company
    from datetime import datetime, timezone

    row = {
        "Company Name": "Belkins",
        "ATS Type": "lever",
        "Slug": "belkins",
        "Status": "active",
        "Date Added": "",
        "Last Scanned": "",
    }
    now_str = datetime.now(timezone.utc).isoformat()

    with patch("src.ats_scraper.requests.get", side_effect=Exception("connection error")):
        jobs, updates = _scan_company(row, 3, lookback_days=3,
                                      detection_order=["lever"], now_str=now_str)

    assert jobs == []
    assert updates == []


def test_fetch_watchlist_jobs_uses_configured_workers():
    """fetch_watchlist_jobs passes scan_workers from config to ThreadPoolExecutor."""
    from src.ats_scraper import fetch_watchlist_jobs

    rows = [{"Company Name": "Ogilvy", "ATS Type": "greenhouse", "Slug": "ogilvy",
             "Status": "active", "Date Added": "", "Last Scanned": ""}]
    config = {
        "watchlist": {
            "enabled": True,
            "lookback_days": 3,
            "scan_workers": 5,
            "detection_order": ["greenhouse"],
        }
    }
    ws = _mock_worksheet(rows)
    ws.batch_update = MagicMock()

    with patch("src.ats_scraper._get_watchlist_worksheet", return_value=ws), \
         patch("src.ats_scraper._scan_company", return_value=([], [])), \
         patch("src.ats_scraper.as_completed", return_value=[]), \
         patch("src.ats_scraper.ThreadPoolExecutor") as mock_executor_cls:

        mock_executor = MagicMock()
        mock_executor.__enter__ = MagicMock(return_value=mock_executor)
        mock_executor.__exit__ = MagicMock(return_value=False)
        mock_executor.submit.return_value = MagicMock()
        mock_executor_cls.return_value = mock_executor

        fetch_watchlist_jobs(config)

    mock_executor.submit.assert_called_once()
    mock_executor_cls.assert_called_once_with(max_workers=5)
