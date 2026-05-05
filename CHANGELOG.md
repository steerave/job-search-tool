# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- ATS Watchlist scanner — directly queries company ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, BambooHR) for jobs not syndicated to job boards
- Watchlist company management via Google Sheet "Watchlist" tab — add a company name and the tool auto-detects its ATS type and slug on the next run
- ATS auto-detection with slug candidate probing — handles company name variants (Inc., Agency, LLC suffixes)
- Remote job filtering per ATS using platform-native fields (isRemote flag, workplaceType, location text)
- Recency filtering (`lookback_days` config) to avoid reprocessing old postings each daily run
- Watchlist results tagged "ATS Watchlist" in Google Sheets Search Type column, flowing through existing dedup → score → sheets → email pipeline
- Feedback analysis pipeline (`analyze_feedback.py`) — reads user scoring from Job Tracker and Job Status sheets
- Target role profile generation — Claude analyzes feedback patterns to build nuanced role preferences
- Automatic config.yaml refinement — adds new job titles and keywords based on user scoring patterns
- Asymmetric change rules — aggressive on adding new search terms, conservative on removing (explicit user request only)
- Config change audit trail (`logs/config_changes.log`)
- Signal-based skip logic — only runs analysis when 5+ new feedback signals exist
- `--force` and `--dry-run` flags for manual control
- Target role profile injection into fit scoring prompt for smarter job matching
- `run_feedback.bat` for Windows Task Scheduler scheduling
- Local QC location post-filter: drops jobs whose reported location doesn't match known Quad Cities-area cities after scraping. Fixes JobSpy ignoring the radius parameter. Configurable via `local_qc.location_include` in config.yaml.
- Title domain pre-filter: skips Claude scoring for jobs with no domain-relevant words in the title (e.g. "Senior Art Director", "iOS Software Engineer"). Catches off-target results from watchlist/local-QC that bypass required_keywords. Configurable via `title_domain_words`.
- `max_jobs_to_score` cap (default 150): hard ceiling on Claude API calls per run with a log warning when hit. Truncates by insertion order; cap-truncated jobs retry on future runs.
- `scripts/log_summary.py`: parses pipeline logs and prints a compact summary — scraped counts by search type, filter stats, scored jobs, sheet additions, estimated API cost with caching, and any errors. Accepts an optional date argument (defaults to today).
- `/project:diagnose-run` Claude Code command: runs the summary script, evaluates metrics against health thresholds, identifies root causes from the log, and delivers specific actionable recommendations. Replaces manual 80K-token log reads during debugging sessions.
- API cost logging: every Claude API call now appends one line to `logs/api_costs.log` with datetime, caller, model, token breakdown (input / cache-write / cache-read / output), and USD cost. Zero overhead — reads `response.usage` already returned by the SDK.
- `/api-cost-report` global Claude Code skill: reads `logs/api_costs.log` and reports total spend, cost by caller, cost by day, and top expensive calls. Works with any project using the same log format.
- Senior / technical Project Manager titles (Senior PM, Technical PM, Senior Technical PM, IT PM, Senior IT PM, Software PM, Project Manager) added to national remote search — broader coverage for remote PM roles.
- `production` and `project` added to `title_domain_words` so generic "Project Manager" and "Producer" titles from watchlist/local-QC pass the pre-scoring title filter.

### Changed
- Watchlist ATS scan now runs companies in parallel (configurable `scan_workers`, default 10), reducing scan time from 10+ minutes to ~65 seconds for 650 companies
- Fit scorer now uses prompt caching (`cache_control: ephemeral`) for the candidate profile system prompt. Profile is built once per batch — subsequent calls pay ~10% for the cached portion, reducing input token cost ~85% on a typical run.

### Fixed
- Config updater YAML indentation — new entries now preserve correct formatting
- Config suggestion JSON parsing — increased max_tokens to prevent truncation, added fallback parser to recover partial responses
- Manual pipeline runs failing silently when launching shell pre-sets `ANTHROPIC_API_KEY=""` (or any other `.env` key to empty). `load_dotenv()` now uses `override=True` so `.env` always wins. Daily 5am Task Scheduler runs unaffected (clean env).
