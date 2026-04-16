# Project Status Log

## 2026-04-16

**Done:**
- Diagnosed root cause of today's 5am credit burn: 259 Claude API calls with no caching, plus 30+ non-local jobs scored under Local QC due to JobSpy ignoring the radius parameter
- Added location post-filter to `scrape_local_qc()` — drops results whose location doesn't match QC-area city/state patterns (`local_qc.location_include` in config.yaml)
- Added title domain pre-filter in `main.py` (`_filter_scoreable_jobs`) — skips Claude scoring for off-target titles like "iOS Software Engineer"; configurable via `title_domain_words`
- Added `max_jobs_to_score: 150` cap in `main.py` — hard ceiling on Claude API calls per run with log warning; cap-truncated jobs retry on future runs
- Rewrote `src/fit_scorer.py` to use prompt caching (`cache_control: ephemeral`) — profile system prompt built once per batch, ~85% input token cost reduction on subsequent calls
- Fixed: domain-skipped jobs now marked as seen so they don't re-enter the pipeline on every run
- Built `scripts/log_summary.py` — parses pipeline logs in ~0.1s, prints compact report: scraped by type, filter stats, scored jobs, sheet additions, estimated API cost with caching, errors
- Added `/project:diagnose-run` Claude Code command (`.claude/commands/diagnose-run.md`) — structured health check with thresholds, root cause analysis, and recommendations; replaces manual 80K-token log reads
- Added `.claude/commands/` to `.gitignore` exception so project commands are version-controlled
- 153 tests passing (added 9 location filter tests, 7 pre-filter tests, 11 caching structure tests, 33 log summary tests)

**In Progress:**
- Nothing

**Next:**
- Monitor tomorrow's 5am run to confirm: local QC results are genuinely QC-area, cost is under $1.50, cap not hit
- Implement hooks discussed this session: config YAML validation hook, test runner hook, pipeline auto-summary hook
- Add `estimate-costs` project-level skill (item 6 from priority list)
- Start career strategy expansion: multi-profile AI search, career-advisor skill, networking tracker

**Notes:**
- Root cause today: JobSpy ignores `distance` radius on most boards — local search must be filtered post-scrape, not at query time
- Prompt caching requires Anthropic SDK ≥ 0.28; `cache_control` on system prompt blocks, not messages

## 2026-04-11

**Done:**
- Diagnosed 5am run: pipeline was not crashing — watchlist scan of 650+ companies took 30+ min serially, email arrived late
- Designed and implemented parallel watchlist ATS scanning using `ThreadPoolExecutor` (`src/ats_scraper.py`)
- Extracted `_scan_company()` worker (self-contained, returns `(jobs, updates)` tuples); main thread merges and batch-writes
- Added `watchlist.scan_workers: 10` to `config.yaml` — expected scan time ~65s vs 10+ min serial
- Added 3 new unit tests (TDD): worker return values, fetch failure handling, executor worker count — 93 total passing
- Wrote design spec (`docs/superpowers/specs/2026-04-11-parallel-watchlist-scanning-design.md`) and implementation plan (`docs/superpowers/plans/2026-04-11-parallel-watchlist-scanning.md`)
- Updated README and CHANGELOG with `scan_workers` config documentation

**In Progress:**
- Nothing

**Next:**
- Monitor tomorrow's 5am run to confirm watchlist scan completes in ~1-2 min and email arrives on time
- Address remaining tech debt: refactor duplicated GSheets auth logic between `ats_scraper.py` and `sheets_updater.py`
- Start career strategy expansion: multi-profile AI search, career-advisor skill, networking tracker

**Notes:**
- `scan_workers` defaults to 10 — tunable in `config.yaml` if rate limiting is observed on any ATS

## 2026-04-10

**Done:**
- Fixed Google Sheets 429 rate limit in watchlist scanner: worksheet object cached per run (was re-authenticating per company), all sheet writes batched into single `ws.batch_update()` call
- Fixed orphaned YAML entries in `config.yaml`: 18 items were being parsed as `required_keywords` but should be `exclude_keywords` (functional bug); 5 that conflicted with active job title searches were dropped entirely
- Removed AI-related terms from `exclude_keywords` (`AI strategy`, `agentic AI`, `GenAI`, `artificial intelligence`) — these shouldn't disqualify a JD
- Added `agencies/` to `.gitignore` and committed agency experience bonus in `fit_scorer.py` prompt (R/GA, AKQA, Verndale agency background treated as positive signal)
- Fixed cross-source duplicate jobs: `deduplicator.py` now normalizes company names (strips Inc./LLC/Corp.) and titles (strips Sr./of/punctuation) before hashing — catches same job from LinkedIn + ATS Watchlist with slightly different strings
- Rewrote README as portfolio-grade documentation with "Design Decisions Worth Explaining" section covering ATS Watchlist sourcing rationale, asymmetric feedback loop, and rate limit architecture
- First scheduled 5am run with ATS Watchlist completed successfully: 384 scraped, 124 new, 12 added to sheet, email delivered at 05:51

**In Progress:**
- Nothing

**Next:**
- Address remaining tech debt: refactor duplicated GSheets auth logic between `ats_scraper.py` and `sheets_updater.py`
- Monitor tomorrow's run for duplicate reduction (dedup hash changed; seen_jobs.json will rebuild with new hashes on next run)
- Start career strategy expansion: multi-profile AI search, career-advisor skill, networking tracker

**Notes:**
- `seen_jobs.json` uses old dedup hashes — first run after today's fix may briefly re-surface a small number of previously-seen jobs; normalizes after one run
- Full run with 727-company watchlist takes ~51 min (ATS detection now cached for all companies; time is mainly job board scraping)

## 2026-04-09

**Done:**
- Built `src/ats_scraper.py` — full ATS watchlist scanner with 6 adapters (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, BambooHR)
- ATS auto-detection: probes endpoints using slug candidates generated from company names, caches result back to Google Sheet
- Per-ATS remote detection (uses platform-native fields: `isRemote`, `workplaceType`, location text), date extraction, and job normalization to standard 14-field dict via shared `_make_job()` helper
- Google Sheets "Watchlist" tab read/write: `read_watchlist()`, `update_watchlist_detection()`, `update_watchlist_last_scanned()`
- `fetch_watchlist_jobs()` orchestrator: reads watchlist, detects unknowns, fetches remote jobs within `lookback_days`, returns normalized dicts
- Integrated into `job_scraper.py` via `scrape_watchlist()` + updated `scrape_all_jobs()` — watchlist is now a third job source alongside national_remote and local_qc
- 43 unit tests in `tests/test_ats_scraper.py` covering all adapters, remote detectors, normalizers, auto-detection, and orchestrator
- End-to-end dry run confirmed: Apple/Microsoft/Amazon → smartrecruiters, Ogilvy → greenhouse — all detected and written back to sheet
- Populated Watchlist Google Sheet tab with 727 companies (ready for first full detection run)

**In Progress:**
- Nothing — feature is complete and pushed

**Next:**
- Run `python main.py --dry-run` tonight to pre-cache ATS detection for all 727 companies (avoids 15-30 min detection overhead on tomorrow's 5am scheduled run)
- Address two tech debt items: (1) duplicated GSheets auth logic between `ats_scraper.py` and `sheets_updater.py`, (2) orphaned YAML entries in `config.yaml`
- Start career strategy expansion: multi-profile AI search, career-advisor skill, networking tracker

**Notes:**
- First run with 727 unknown companies will take 15-30 min for ATS detection; subsequent runs fast (detection cached in sheet)
- ATS coverage estimate: ~55-65% of list; Workday/iCIMS companies already covered by JobSpy scrape via LinkedIn/Indeed syndication
- Plan saved at `docs/superpowers/plans/2026-04-09-ats-watchlist-scanner.md`

## 2026-04-03

**Done:**
- Fixed config_updater truncated JSON parsing — increased max_tokens from 2000 to 4096 and added fallback parser to recover suggestions from partial responses
- Ran first real feedback analysis: 17 new signals processed, 34 config changes applied (12 job titles, 10 required keywords, 12 exclude keywords)
- Target role profile regenerated from tracker feedback and application history
- Created Windows Task Scheduler task "Job Search Feedback Analysis" for daily 6am runs
- Added 2 new tests for truncated JSON recovery in config_updater

**In Progress:**
- config.yaml, profile/target_role_profile.md, and data/last_analysis.json updated by feedback analysis but not yet committed

**Next:**
- Commit feedback analysis results and bug fix
- Start career strategy expansion: multi-profile AI search, career-advisor skill, networking tracker

**Notes:**
- The 6am feedback task was never scheduled before today — only the 5am main search was in Task Scheduler
- Feedback analysis confirmed working end-to-end with real sheet data (70 tracker rows, 56 status rows)

## 2026-04-01

**Done:**
- Added feedback_reader module — reads Google Sheets feedback and counts signals
- Added profile_generator — Claude-powered target role profiling from resume + feedback
- Injected target role profile into fit scoring prompt for better job matching
- Added config_updater — asymmetric config.yaml updates driven by feedback analysis
- Added analyze_feedback.py entry point for daily feedback analysis pipeline
- Fixed Windows UTF-8 logging and increased config suggestion max_tokens
- Fixed config updater YAML indentation; added run_feedback.bat launcher
- Updated README, CLAUDE.md, and CHANGELOG for feedback analysis feature
- Created `/status` skill and added Daily Status Log standard to global CLAUDE.md

**In Progress:**
- config.yaml has uncommitted local changes (likely from config_updater testing)

**Next:**
- Wire feedback analysis into daily pipeline schedule (Windows Task Scheduler)
- Start career strategy expansion: multi-profile AI search, career-advisor skill, networking tracker
- Test full feedback analysis loop end-to-end with real data
