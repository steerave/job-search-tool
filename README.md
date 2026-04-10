# AI Job Pipeline

Automated data pipeline that scrapes job listings daily, scores them with Claude AI using a self-improving feedback loop, syncs results to Google Sheets, and delivers a morning email digest.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Scheduler (5am daily)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Job Scraper (JobSpy)                                        │
│  • Multi-board scraping (LinkedIn, Indeed, Glassdoor, etc.)  │
│  • Deduplication via seen_jobs.json                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  LLM Scoring Layer (Claude API)                              │
│  • Fit score 1–10 against target role profile                │
│  • Structured rationale output                               │
│  • Resume tailoring + cover letter generation (above threshold)│
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────┐   ┌─────────────────┐
│  Google Sheets Sync                   │   │  Email Digest   │
│  • Formatted output with color coding │   │  • Top matches  │
│  • Status tracking columns            │   │  • Score summary│
└───────────────────────────────────────┘   └─────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  Feedback Loop (6am daily)                   │
│  • Reads user scores from tracker                           │
│  • Generates/updates target role profile (LLM)              │
│  • Auto-refines search config (asymmetric: add freely,      │
│    remove conservatively)                                    │
│  • Logs all config changes to audit trail                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

- **Multi-source scraping** — pulls from job boards (LinkedIn, Indeed, Google Jobs, ZipRecruiter) via JobSpy
- **ATS Watchlist** — directly queries company ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, BambooHR) for roles not syndicated to job boards; companies managed via a Google Sheet tab with auto-detection of ATS type
- **LLM-based fit scoring** — Claude scores each job 1–10 against a dynamically-maintained role profile
- **Self-improving feedback loop** — scores you provide feed back into search config and role profile refinement
- **Document generation** — tailored resume and cover letter for top matches (above configurable threshold)
- **Google Sheets integration** — structured output with color-coded scores, status tracking, filtering
- **Email digest** — daily morning summary of top matches
- **Asymmetric config updates** — aggressive on adding new search terms, conservative on removing existing ones
- **Audit trail** — all config changes logged with reasoning

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

Edit `config.yaml` to set target job titles, required/excluded keywords, score thresholds, and document generation cutoff.

### 7. Run setup

```bash
python setup.py
```

This parses your resume and LinkedIn data into `profile/parsed_profile.json`, initializes the Google Sheet with headers and formatting, and validates your config.

### 8. Test run

```bash
python main.py --dry-run
```

Scrapes and scores without writing anything. Verify output looks correct before scheduling.

### 9. Schedule

Run `main.py` daily (e.g., 5am) and `analyze_feedback.py` daily (e.g., 6am) via your system scheduler.

**Windows Task Scheduler:** Create Basic Task → Daily trigger → `python /path/to/main.py`

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

---

## Feedback Loop Design

The system learns from your manual scoring. Rate jobs in the `My Score` column (1–5) and the feedback analyzer uses these signals to:

1. **Update the target role profile** (`profile/target_role_profile.md`) — a nuanced description of your ideal role used by the LLM scorer
2. **Refine search config** (`config.yaml`) — adds job titles and keywords when patterns emerge

**Asymmetric update policy:** new terms are added after 2+ signals; existing terms are only removed with explicit instruction (e.g., a note like "exclude ecommerce roles"). This prevents useful search terms from being dropped on noise.

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
├── config.yaml                   # Search preferences
├── requirements.txt
├── main.py                       # Pipeline entry point
├── setup.py                      # One-time setup
├── analyze_feedback.py           # Feedback analysis
├── src/
│   ├── job_scraper.py            # JobSpy scraping
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
│   └── target_role_profile.md    # Generated by feedback analyzer
├── templates/
│   ├── resume_template.docx      # Generated by setup.py
│   └── cover_letter_template.docx
├── output/YYYY/MM/               # Generated documents
├── data/seen_jobs.json           # Deduplication store
├── data/last_analysis.json       # Feedback analysis state
└── logs/YYYY-MM-DD.log           # Daily logs
```

---

## Google Sheets Output Schema

| Column | Description |
|---|---|
| Date Found | When the job was scraped |
| Search Type | Search profile that found it |
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

The pipeline is designed to minimize token usage:

- **Fit scoring runs on every job** — uses a compact prompt with the target role profile as context
- **Document generation is threshold-gated** — only jobs above `doc_generation_score` in `config.yaml` trigger resume tailoring and cover letter generation (the expensive operations)
- **Feedback analysis skips low-signal days** — only runs when 5+ new scored jobs or applications exist, avoiding unnecessary LLM calls
- **Config update batching** — all search config changes are batched into a single LLM call per feedback run

Typical usage at default settings: ~$0.05–$0.15 per generated document set. Tune `max_docs_per_day` and `doc_generation_score` in `config.yaml` to control costs.

---

## Troubleshooting

**No jobs found:** JobSpy can be rate-limited by job boards periodically. Check `logs/YYYY-MM-DD.log` for details and retry in a few hours.

**Google Sheets auth error:** Verify the sheet is shared with your service account email and both Sheets and Drive APIs are enabled.

**Email not sending:** Use an App Password (not your regular password) for Gmail. Requires 2-Step Verification enabled.

**Claude API error:** Verify `ANTHROPIC_API_KEY` is correct and check usage at [console.anthropic.com](https://console.anthropic.com).

**Profile parsing issues:** Manually edit `profile/parsed_profile.json` — the LLM uses this directly so accuracy matters.
