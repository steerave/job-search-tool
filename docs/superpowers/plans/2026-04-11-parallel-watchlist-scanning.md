# Parallel Watchlist Scanning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the serial company-by-company watchlist scan with a parallel ThreadPoolExecutor-based scan to reduce runtime from 10+ minutes to ~65 seconds.

**Architecture:** Extract per-company logic from `fetch_watchlist_jobs` into a self-contained `_scan_company` worker that returns `(jobs, updates)` tuples. A `ThreadPoolExecutor` runs all workers concurrently. The main thread merges results and does a single batch Google Sheets write — identical to today.

**Tech Stack:** Python `concurrent.futures.ThreadPoolExecutor`, existing `requests`, `gspread`, PyYAML config.

**Spec:** `docs/superpowers/specs/2026-04-11-parallel-watchlist-scanning-design.md`

---

## File Map

| File | Change |
|---|---|
| `src/ats_scraper.py` | Add `_scan_company()`, rewrite `fetch_watchlist_jobs()` loop |
| `config.yaml` | Add `scan_workers: 10` under `watchlist:` |
| `tests/test_ats_scraper.py` | Add 3 new tests for `_scan_company` and parallel assembly |

---

### Task 1: Add `scan_workers` to config.yaml

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: Add the config key**

Open `config.yaml`. Find the `watchlist:` section (currently has `enabled`, `lookback_days`, `detection_order`). Add `scan_workers: 10` as the last item in that block:

```yaml
watchlist:
  enabled: true
  lookback_days: 3
  scan_workers: 10
  detection_order:
    - greenhouse
    - lever
    - ashby
    - smartrecruiters
    - recruitee
    - bamboohr
```

- [ ] **Step 2: Verify config loads cleanly**

```bash
cd "C:/Users/steerave/Desktop/Claude Projects/Job Search Tool"
python -c "import yaml; c = yaml.safe_load(open('config.yaml')); print(c['watchlist']['scan_workers'])"
```

Expected output: `10`

- [ ] **Step 3: Commit**

```bash
git add config.yaml
git commit -m "config: add scan_workers to watchlist config (default 10)"
```

---

### Task 2: Write tests for `_scan_company`

**Files:**
- Modify: `tests/test_ats_scraper.py`

These tests must be written BEFORE the implementation (TDD). They will fail until Task 3 is complete.

- [ ] **Step 1: Add the three new tests at the bottom of `tests/test_ats_scraper.py`**

```python
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
    from concurrent.futures import ThreadPoolExecutor

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
         patch("src.ats_scraper._scan_company", return_value=([], [])) as mock_scan, \
         patch("src.ats_scraper.ThreadPoolExecutor") as mock_executor_cls:

        mock_executor = MagicMock()
        mock_executor.__enter__ = MagicMock(return_value=mock_executor)
        mock_executor.__exit__ = MagicMock(return_value=False)
        mock_executor.submit.return_value = MagicMock()
        mock_executor_cls.return_value = mock_executor

        fetch_watchlist_jobs(config)

    mock_executor_cls.assert_called_once_with(max_workers=5)
```

- [ ] **Step 2: Run the new tests to confirm they fail (function not yet defined)**

```bash
cd "C:/Users/steerave/Desktop/Claude Projects/Job Search Tool"
python -m pytest tests/test_ats_scraper.py::test_scan_company_returns_jobs_and_update tests/test_ats_scraper.py::test_scan_company_returns_empty_on_fetch_failure tests/test_ats_scraper.py::test_fetch_watchlist_jobs_uses_configured_workers -v
```

Expected: 3 FAILED with `ImportError: cannot import name '_scan_company'`

---

### Task 3: Implement `_scan_company` and rewrite `fetch_watchlist_jobs`

**Files:**
- Modify: `src/ats_scraper.py`

- [ ] **Step 1: Add `from concurrent.futures import ThreadPoolExecutor, as_completed` to imports**

At the top of `src/ats_scraper.py`, find the existing imports block and add:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

- [ ] **Step 2: Add `_scan_company` function**

Insert this function just before `fetch_watchlist_jobs` (around line 475), replacing nothing:

```python
def _scan_company(
    row: dict,
    row_index: int,
    lookback_days: int,
    detection_order: list[str],
    now_str: str,
) -> tuple[list[dict], list[dict]]:
    """
    Process a single watchlist company. Thread-safe — owns no shared state.
    Returns (jobs, sheet_updates) where sheet_updates is a list of gspread
    batch_update entry dicts (0, 1, or 2 entries per company).
    """
    company_name = row.get("Company Name", "").strip()
    ats_type = row.get("ATS Type", "unknown").strip().lower()
    slug = row.get("Slug", "").strip()
    status = row.get("Status", "active").strip().lower()

    if not company_name or status == "paused":
        return [], []

    updates: list[dict] = []

    # Auto-detect ATS for unknown companies
    if ats_type in ("unknown", ""):
        logger.info(f"[Watchlist] Detecting ATS for: {company_name}")
        detected_ats, detected_slug = detect_ats(company_name, detection_order)
        if detected_ats:
            ats_type = detected_ats
            slug = detected_slug
            updates.append({"range": f"B{row_index}:E{row_index}",
                            "values": [[ats_type, slug, "active", now_str]]})
        else:
            return [], [{"range": f"B{row_index}:E{row_index}",
                         "values": [["not_detected", "", "active", now_str]]}]

    if ats_type == "not_detected":
        return [], []

    fetch_fn = ATS_ADAPTERS.get(ats_type)
    normalizer = NORMALIZERS.get(ats_type)
    if not fetch_fn or not normalizer:
        logger.warning(f"[Watchlist] Unknown ATS type '{ats_type}' for {company_name}")
        return [], []

    try:
        raw_jobs = fetch_fn(slug)
        if raw_jobs is None:
            logger.warning(f"[Watchlist] Fetch failed: {ats_type}/{slug} ({company_name})")
            return [], updates

        remote_detector = REMOTE_DETECTORS[ats_type]
        date_extractor = DATE_EXTRACTORS[ats_type]
        jobs = [
            normalizer(raw, company_name)
            for raw in raw_jobs
            if remote_detector(raw) and _is_within_days(date_extractor(raw), lookback_days)
        ]

        logger.info(f"[Watchlist] {company_name} ({ats_type}): {len(jobs)} new remote jobs")
        updates.append({"range": f"F{row_index}", "values": [[now_str]]})
        return jobs, updates

    except Exception as e:
        logger.error(f"[Watchlist] Error processing {company_name}: {e}")
        return [], updates
```

- [ ] **Step 3: Rewrite `fetch_watchlist_jobs`**

Replace the entire `fetch_watchlist_jobs` function (lines 475–563 in the current file) with:

```python
def fetch_watchlist_jobs(config: dict) -> list[dict]:
    """
    Read companies from the Watchlist Google Sheet tab, auto-detect ATS for unknowns,
    fetch remote jobs posted within lookback_days, and return normalized job dicts.

    Each returned job has the 14 standard fields. The caller (scrape_watchlist in
    job_scraper.py) adds search_type='watchlist' before returning.

    Companies are scanned in parallel (scan_workers from config, default 10).
    All Google Sheets writes are batched into a single API call at the end.
    """
    watchlist_cfg = config.get("watchlist", {})
    if not watchlist_cfg.get("enabled", True):
        return []

    lookback_days = watchlist_cfg.get("lookback_days", 3)
    detection_order = watchlist_cfg.get("detection_order", list(ATS_ADAPTERS.keys()))
    scan_workers = watchlist_cfg.get("scan_workers", 10)

    companies = read_watchlist(config)
    now_str = datetime.now(timezone.utc).isoformat()

    logger.info(f"[Watchlist] Scanning {len(companies)} companies with {scan_workers} workers")

    # Pre-warm worksheet cache in main thread so workers find it already populated
    _get_watchlist_worksheet(config)

    all_jobs: list[dict] = []
    pending_updates: list[dict] = []

    with ThreadPoolExecutor(max_workers=scan_workers) as executor:
        futures = {
            executor.submit(
                _scan_company, row, i, lookback_days, detection_order, now_str
            ): i
            for i, row in enumerate(companies, start=2)
        }
        for future in as_completed(futures):
            try:
                jobs, updates = future.result()
                all_jobs.extend(jobs)
                pending_updates.extend(updates)
            except Exception as e:
                row_index = futures[future]
                logger.error(f"[Watchlist] Unexpected worker error at row {row_index}: {e}")

    # Flush all sheet writes in one batch call
    if pending_updates:
        ws = _get_watchlist_worksheet(config)
        ws.batch_update(pending_updates)
        logger.info(f"[Watchlist] Wrote {len(pending_updates)} sheet updates in one batch")

    logger.info(f"[Watchlist] Total raw jobs fetched: {len(all_jobs)}")
    return all_jobs
```

- [ ] **Step 4: Run the three new tests — they should now pass**

```bash
cd "C:/Users/steerave/Desktop/Claude Projects/Job Search Tool"
python -m pytest tests/test_ats_scraper.py::test_scan_company_returns_jobs_and_update tests/test_ats_scraper.py::test_scan_company_returns_empty_on_fetch_failure tests/test_ats_scraper.py::test_fetch_watchlist_jobs_uses_configured_workers -v
```

Expected: 3 PASSED

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
python -m pytest tests/ -v
```

Expected: all previously passing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/ats_scraper.py tests/test_ats_scraper.py
git commit -m "feat: parallel watchlist ATS scanning with ThreadPoolExecutor

Replaces serial company loop with concurrent.futures.ThreadPoolExecutor.
Extracts _scan_company() worker (self-contained, returns jobs + sheet updates).
Main thread merges results and does single batch Sheets write as before.
Configurable via watchlist.scan_workers (default 10).
Expected: ~65s scan time vs 10+ min serial.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Update README and CHANGELOG

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update CHANGELOG.md**

Under `## [Unreleased]`, add under `### Changed`:

```markdown
### Changed
- Watchlist ATS scan now runs companies in parallel (configurable `scan_workers`, default 10), reducing scan time from 10+ minutes to ~65 seconds for 650 companies
```

- [ ] **Step 2: Update README.md**

Find the section in README that describes the watchlist or daily pipeline. Add a note about `scan_workers`. Under the `config.yaml` reference or watchlist section, add:

```markdown
- `watchlist.scan_workers` — parallel workers for ATS scanning (default: `10`)
```

- [ ] **Step 3: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: document parallel watchlist scan_workers config option

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Push and verify

- [ ] **Step 1: Push to GitHub**

```bash
git push
```

- [ ] **Step 2: Smoke-test with dry-run**

```bash
python main.py --dry-run
```

Watch the log for:
```
[Watchlist] Scanning N companies with 10 workers
```
And confirm the watchlist section finishes noticeably faster than before.
