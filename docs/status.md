# Project Status Log

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
