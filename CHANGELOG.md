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

### Fixed
- Config updater YAML indentation — new entries now preserve correct formatting
- Config suggestion JSON parsing — increased max_tokens to prevent truncation, added fallback parser to recover partial responses
