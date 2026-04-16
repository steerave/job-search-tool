# AI Job Search Pipeline

An automated, self-improving job discovery engine built for senior-level searches — where the roles you actually want rarely surface on the first page of LinkedIn.

---

## The Problem This Solves

Most job search tools stop at job boards. That works fine for mid-level roles, but senior director and VP-level positions behave differently:

- Many are posted exclusively to a company's own careers page (Greenhouse, Lever, Ashby) and never syndicated to LinkedIn or Indeed
- The ones that do appear on boards are flooded with irrelevant results — the same "Digital Marketing Director" showing up against a search for "Director of Digital Delivery"
- Your own feedback about what's relevant or off-target sits unused, and your search configuration never improves

This pipeline addresses all three. It scrapes job boards, goes directly to company ATS APIs for roles that never syndicate, scores every result against a dynamically maintained profile, and gets smarter every day from your own feedback.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                     Scheduler (5am daily)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
  ┌────────────────┐ ┌──────────────┐ ┌────────────────────┐
  │  Job Boards    │ │  Local Market│ │  ATS Watchlist     │
  │  (JobSpy)      │ │  (Quad Cities│ │  Direct API queries│
  │  LinkedIn      │ │  50mi radius)│ │  to company career │
  │  Indeed        │ │              │ │  pages (Greenhouse,│
  │  Google Jobs   │ │              │ │  Lever, Ashby,     │
  │  ZipRecruiter  │ │              │ │  SmartRecruiters,  │
  └────────┬───────┘ └──────┬───────┘ │  Recruitee,        │
           │                │         │  BambooHR)         │
           └────────────────┴─────────┴──┐
                                         ▼
                         ┌───────────────────────────┐
                         │  Deduplication             │
                         │  Seen job tracking (90d)   │
                         └──────────────┬────────────┘
                                        ▼
                         ┌───────────────────────────┐
                         │  LLM Fit Scoring (Claude)  │
                         │  Score 1–10 vs. role       │
                         │  profile + feedback history│
                         └──────────────┬────────────┘
                                        ▼
                  ┌─────────────────────┴──────────────┐
                  ▼                                     ▼
     ┌────────────────────────┐           ┌─────────────────────┐
     │  Google Sheets         │           │  Email Digest       │
     │  Color-coded scores    │           │  Top matches, 6am   │
     │  Status tracking       │           └─────────────────────┘
     │  Filtering + notes     │
     └────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  Feedback Loop (6am daily)                   │
│  Reads your manual scores → updates role profile (LLM) →    │
│  refines search config → logs all changes to audit trail     │
└─────────────────────────────────────────────────────────────┘
```

---

## Design Decisions Worth Explaining

### Going Directly to the Source: ATS Watchlist

Job boards are aggregators. For senior roles at specific target companies, the canonical source is the company's own ATS. A role posted to Greenhouse at R/GA may never appear on LinkedIn — or may appear days later with degraded metadata.

The ATS Watchlist scanner maintains a curated list of 700+ target companies (managed via a Google Sheet tab) and queries their career APIs directly on each run. On first encounter, it auto-detects which ATS platform a company uses by probing endpoints with slug candidates generated from the company name. Detection results are cached back to the sheet so subsequent runs are near-instant.

This shifts the source of truth from "what job boards chose to index" to "what companies actually posted."

### A Search Config That Learns

Most automated search tools have a static config: you set keywords once and forget them. The problem is that you learn what you actually want by seeing what you don't want — a search that surfaces 50 roles teaches you 10 things to add and 5 to exclude.

The feedback analyzer runs each morning after the main scrape. It reads your manual scores from the tracker sheet (1–5 rating scale), identifies patterns, and updates both a target role profile document and the keyword configuration. The update policy is intentionally asymmetric:

- **Adding new terms:** triggered after 2+ confirming signals
- **Removing existing terms:** only with explicit instruction

This asymmetry matters. A useful search term that appears in a rare but highly relevant role shouldn't get dropped because it also appears in three off-target results. Conservative removal prevents useful signal from being pruned on noise.

### Rate Limiting at Scale

Running 700+ ATS company checks daily means thousands of HTTP requests and dozens of Google Sheets API calls. Early versions hit quota limits (429 errors) because each company detection triggered independent sheet reads and writes.

Fixed by two changes:
1. **Worksheet caching** — the Google Sheets connection is opened once per run rather than once per company
2. **Batched writes** — all sheet updates (ATS detection results, last-scanned timestamps) are collected during the run and flushed as a single API call at the end

The run now completes in under an hour for 700+ companies with no quota errors.

---

## Features

- **Multi-source job scraping** — LinkedIn, Indeed, Google Jobs, ZipRecruiter via JobSpy
- **ATS Watchlist** — direct API queries to Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, and BambooHR for roles never syndicated to job boards
- **ATS auto-detection** — add a company name to the watchlist; the tool figures out which ATS they use on the next run
- **LLM fit scoring** — Claude scores each job 1–10 against a dynamically maintained role profile (not just keyword matching)
- **Self-improving feedback loop** — your manual scores drive daily config refinement and role profile updates
- **Asymmetric config updates** — aggressive on adding new search terms, conservative on removing (prevents signal loss)
- **Document generation** — tailored resume and cover letter for top matches above a configurable score threshold
- **Google Sheets integration** — color-coded scores, status tracking, filtering, manual note columns
- **Email digest** — daily morning summary of top matches
- **Audit trail** — every automated config change is logged with reasoning to `logs/config_changes.log`
- **Token efficiency** — prompt caching on the candidate profile, a title domain pre-filter, and a configurable per-run scoring cap keep Claude API costs predictable on busy scrape days.
- **Local QC quality** — location post-filter removes non-local results that JobSpy returns despite the radius setting, keeping Local QC results genuinely local to the Quad Cities area.

---

## One-Time Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/steerave/ai-job-pipeline.git
cd ai-job-pipeline
pip install -r requirements.txt
```

### 2. Get an Anthropic API Key

Go to [console.anthropic.com](https://console.anthropic.com) → API Keys → Create key.

### 3. Set up Google Sheets API

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project and enable: **Google Sheets API** + **Google Drive API**
3. Go to **IAM & Admin → Service Accounts** → Create Service Account
4. Click the service account → **Keys → Add Key → JSON** → Download
5. Create a new Google Sheet and share it with the service account email (Editor access)
6. Copy the Sheet ID from the URL: `docs.google.com/spreadsheets/d/SHEET_ID/edit`

### 4. Add your resume and LinkedIn export

```
profile/resume.pdf              # or resume.docx
profile/linkedin_export/        # CSV files from LinkedIn data export
```

**LinkedIn export:** Settings & Privacy → Data Privacy → Get a copy of your data → Fast file (Profile, Positions, Skills, Education)

### 5. Configure `.env`

Copy `.env.template` to `.env` and fill in your values:

```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_SHEETS_ID=your_sheet_id
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service_account.json
GOOGLE_JOB_STATUS_SHEET_ID=your_status_sheet_id
EMAIL_SENDER=your@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECIPIENT=your@email.com
```

### 6. Customize `config.yaml`

Edit `config.yaml` to set target job titles, required/excluded keywords, score thresholds, and document generation cutoff. You can edit this file directly at any time — it is the single source of truth for search configuration.

Key configuration options:
- `job_titles` — target job titles passed to JobSpy
- `required_keywords`, `exclude_keywords` — filter jobs by title and description
- `min_fit_score` — jobs below this score are not added to Google Sheets
- `national_remote` — config for national remote job board search
- `local_qc` — config for local Quad Cities search
- `watchlist.scan_workers` — parallel workers for ATS scanning (default: `10`); improves scan time from 10+ minutes to ~65 seconds for 650 companies
- `watchlist.lookback_days` — only fetch jobs posted within this many days

### 7. Run setup

```bash
python setup.py
```

Parses your resume and LinkedIn data into `profile/parsed_profile.json`, initializes the Google Sheet with headers and formatting, and validates your config.

### 8. Populate the ATS Watchlist

Open your Google Sheet and find the **Watchlist** tab. Add company names in column A — one per row. Leave all other columns blank. On the next run the tool will auto-detect each company's ATS platform and populate the remaining columns.

### 9. Test run

```bash
python main.py --dry-run
```

Scrapes and scores without writing anything. Verify output looks correct before scheduling.

### 10. Schedule

Run `main.py` daily (e.g., 5am) and `analyze_feedback.py` daily (e.g., 6am) via your system scheduler.

**Windows Task Scheduler:** Create Basic Task → Daily trigger → `python /path/to/main.py`

Note: with a large watchlist (700+ companies), the first run takes 45–90 minutes for ATS detection. Subsequent runs are significantly faster as detections are cached.

---

## Commands

### Main pipeline

```bash
# Full run
python main.py

# Preview only (no writes, no email)
python main.py --dry-run

# Custom config/env paths
python main.py --config path/to/config.yaml --env path/to/.env
```

### Feedback analysis

```bash
# Normal run (skips if < 5 new signals)
python analyze_feedback.py

# Force run regardless of signal count
python analyze_feedback.py --force

# Preview changes without writing
python analyze_feedback.py --dry-run
```

### Diagnostic commands

```bash
# Print a compact summary of today's pipeline run
python scripts/log_summary.py

# Print summary for a specific date
python scripts/log_summary.py 2026-04-16
```

In a Claude Code session:

```
/project:diagnose-run          # diagnose today's run
/project:diagnose-run yesterday
```

---

## Feedback Loop Design

The system learns from your manual scoring. Rate jobs in the `My Score` column (1–5) and the feedback analyzer uses these signals to:

1. **Update the target role profile** (`profile/target_role_profile.md`) — a nuanced description of your ideal role used by the LLM scorer
2. **Refine search config** (`config.yaml`) — adds job titles and keywords when patterns emerge

**Asymmetric update policy:** new terms are added after 2+ signals; existing terms are only removed with explicit instruction. This prevents useful search terms from being dropped on noise.

| Score | Signal |
|---|---|
| 5 | Strong positive — strongly shapes profile toward similar roles |
| 4 | Positive — moderate signal |
| 3 | Neutral |
| 2 | Weak negative — lowers priority of similar roles |
| 1 | Strong negative — excluded from profile direction |

---

## Project Structure

```
ai-job-pipeline/
├── .env                          # API keys (never commit)
├── config.yaml                   # Search preferences — edit directly
├── requirements.txt
├── main.py                       # Pipeline entry point
├── setup.py                      # One-time setup
├── analyze_feedback.py           # Feedback analysis entry point (6am)
├── src/
│   ├── job_scraper.py            # JobSpy scraping + watchlist orchestration
│   ├── ats_scraper.py            # ATS watchlist: adapters, detection, normalization
│   ├── deduplicator.py           # Seen job tracking
│   ├── fit_scorer.py             # Claude: job fit scoring
│   ├── resume_tailor.py          # Claude: resume tailoring
│   ├── cover_letter_writer.py    # Claude: cover letter generation
│   ├── document_builder.py       # .docx file creation
│   ├── sheets_updater.py         # Google Sheets integration
│   ├── email_notifier.py         # Email digest
│   └── profile_parser.py         # Resume + LinkedIn parsing
├── profile/
│   ├── resume.pdf                # Input: your resume
│   ├── linkedin_export/          # Input: LinkedIn CSV export
│   ├── parsed_profile.json       # Generated by setup.py
│   └── target_role_profile.md    # Generated + updated by feedback analyzer
├── templates/
│   ├── resume_template.docx      # Generated by setup.py
│   └── cover_letter_template.docx
├── output/YYYY/MM/               # Generated documents
├── data/seen_jobs.json           # Deduplication store
├── data/last_analysis.json       # Feedback analysis state
└── logs/
    ├── YYYY-MM-DD.log            # Daily pipeline logs
    └── config_changes.log        # Automated config change audit trail
```

---

## Google Sheets Output Schema

| Column | Description |
|---|---|
| Date Found | When the job was scraped |
| Search Type | Source: National Remote / Local QC / ATS Watchlist |
| Role Name | Job title |
| Company Name | Employer |
| Employment Type | Full-time, Contract, etc. |
| Remote | Yes / Hybrid / No |
| Compensation | Salary range if available |
| Location | Job location |
| Fit Score | 1–10 (LLM scored) — color coded |
| Fit Notes | LLM rationale for the score |
| Job Description | First 500 chars |
| Direct Link | Apply URL |
| Resume File | Path to tailored resume .docx |
| Cover Letter File | Path to cover letter .docx |
| Status | Manual tracking (New / Applied / Interviewing / Rejected / Offer) |
| Notes | Free-form notes |
| My Score | 1–5 rating (dropdown) — feeds the feedback analyzer |

---

## API Cost Optimization

- **Fit scoring runs on every job** — uses a compact prompt with the target role profile as context
- **Document generation is threshold-gated** — only jobs above `doc_generation_score` in `config.yaml` trigger resume tailoring and cover letter generation (the expensive operations)
- **Feedback analysis skips low-signal days** — only runs when 5+ new scored jobs or applications exist
- **Config update batching** — all search config changes are batched into a single LLM call per feedback run

Typical cost at default settings: ~$0.05–$0.15 per generated document set.

---

## Troubleshooting

**No jobs found:** JobSpy can be rate-limited by job boards periodically. Check `logs/YYYY-MM-DD.log` and retry in a few hours.

**Google Sheets 429 quota error:** The watchlist scanner batches all sheet writes to avoid hitting per-minute limits. If you still see 429 errors on reads, the Google Cloud project may need a quota increase for the Sheets API.

**Email not sending:** Use an App Password (not your regular password) for Gmail. Requires 2-Step Verification enabled.

**Claude API error:** Verify `ANTHROPIC_API_KEY` is correct and check usage at [console.anthropic.com](https://console.anthropic.com).

**Profile parsing issues:** Manually edit `profile/parsed_profile.json` — the LLM uses this directly so accuracy matters.

**Watchlist detection slow on first run:** Expected — 700+ unknown companies each require ATS probing. The first full run takes 45–90 minutes. All detections are cached to the sheet, so subsequent runs skip detection entirely for known companies.
