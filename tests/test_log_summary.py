"""Tests for scripts/log_summary.py parse and format logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from log_summary import parse_log_text, estimate_cost, format_summary


SAMPLE_LOG = """
05:00:01 [INFO] job_scraper - [National Remote] Total after filtering: 361 jobs
05:29:01 [INFO] job_scraper - [Local QC] Location filter: 28 non-local jobs removed
05:29:01 [INFO] job_scraper - [Local QC] Total after filtering: 45 jobs
05:29:03 [INFO] job_scraper - [Watchlist] Total after filtering: 12 jobs
05:30:00 [INFO] __main__ - New: 80 | Duplicates skipped: 338
05:30:01 [INFO] __main__ - Domain pre-filter: 15 off-domain jobs skipped, 65 remain for scoring
06:00:05 [INFO] __main__ - PIPELINE COMPLETE
06:00:05 [INFO] __main__ -   Scraped:         418
06:00:05 [INFO] __main__ -   New (unseen):    80
06:00:05 [INFO] __main__ -   Added to sheet:  22
06:00:05 [INFO] __main__ -   Below threshold: 43
"""

SAMPLE_LOG_WITH_CAP = """
05:30:01 [INFO] __main__ - Domain pre-filter: 5 off-domain jobs skipped, 180 remain for scoring
05:30:02 [WARNING] __main__ - Job count (180) exceeds max_jobs_to_score=150. Truncating.
06:00:05 [INFO] __main__ - PIPELINE COMPLETE
06:00:05 [INFO] __main__ -   Scraped:         760
06:00:05 [INFO] __main__ -   New (unseen):    185
06:00:05 [INFO] __main__ -   Added to sheet:  44
06:00:05 [INFO] __main__ -   Below threshold: 106
"""

SAMPLE_LOG_WITH_ERRORS = """
05:09:27 [ERROR] job_scraper - JobSpy scrape failed for 'Chief of Staff Technology': Invalid country string
05:13:48 [ERROR] job_scraper - JobSpy scrape failed for 'VP Implementation Services': context deadline exceeded
06:00:05 [INFO] __main__ - PIPELINE COMPLETE
06:00:05 [INFO] __main__ -   Scraped:         400
06:00:05 [INFO] __main__ -   New (unseen):    50
06:00:05 [INFO] __main__ -   Added to sheet:  10
06:00:05 [INFO] __main__ -   Below threshold: 30
"""


class TestParseLogText:

    def test_extracts_national_count(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["national"] == 361

    def test_extracts_local_count(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["local"] == 45

    def test_extracts_watchlist_count(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["watchlist"] == 12

    def test_extracts_location_removed(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["loc_removed"] == 28

    def test_location_removed_zero_when_absent(self):
        stats = parse_log_text(SAMPLE_LOG_WITH_CAP)
        assert stats["loc_removed"] == 0

    def test_extracts_scraped_from_summary(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["scraped"] == 418

    def test_extracts_new_unseen(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["new"] == 80

    def test_extracts_added_to_sheet(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["added"] == 22

    def test_extracts_below_threshold(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["below"] == 43

    def test_scored_is_added_plus_below(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["scored"] == 65  # 22 + 43

    def test_extracts_domain_skipped(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["domain_skipped"] == 15

    def test_cap_not_hit(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["cap_hit"] is False
        assert stats["cap_truncated"] == 0

    def test_cap_hit_detected(self):
        stats = parse_log_text(SAMPLE_LOG_WITH_CAP)
        assert stats["cap_hit"] is True

    def test_cap_truncated_count(self):
        stats = parse_log_text(SAMPLE_LOG_WITH_CAP)
        assert stats["cap_truncated"] == 30  # 180 - 150

    def test_no_errors(self):
        stats = parse_log_text(SAMPLE_LOG)
        assert stats["error_count"] == 0

    def test_errors_counted(self):
        stats = parse_log_text(SAMPLE_LOG_WITH_ERRORS)
        assert stats["error_count"] == 2

    def test_error_lines_captured(self):
        stats = parse_log_text(SAMPLE_LOG_WITH_ERRORS)
        assert len(stats["error_lines"]) == 2
        assert "JobSpy scrape failed" in stats["error_lines"][0]

    def test_empty_log(self):
        stats = parse_log_text("")
        assert stats["scraped"] == 0
        assert stats["scored"] == 0
        assert stats["error_count"] == 0


class TestEstimateCost:

    def test_zero_jobs_costs_nothing(self):
        assert estimate_cost(0) == 0.0

    def test_one_job_costs_more_than_zero(self):
        assert estimate_cost(1) > 0.0

    def test_more_jobs_cost_more(self):
        assert estimate_cost(100) > estimate_cost(10)

    def test_reasonable_range_for_150_jobs(self):
        cost = estimate_cost(150)
        assert 0.10 < cost < 2.00

    def test_cost_is_float(self):
        assert isinstance(estimate_cost(50), float)


class TestFormatSummary:

    def _stats(self):
        return parse_log_text(SAMPLE_LOG)

    def test_contains_date(self):
        result = format_summary(self._stats(), "2026-04-16")
        assert "2026-04-16" in result

    def test_contains_scraped_count(self):
        result = format_summary(self._stats(), "2026-04-16")
        assert "418" in result

    def test_contains_scored_count(self):
        result = format_summary(self._stats(), "2026-04-16")
        assert "65" in result

    def test_contains_added_count(self):
        result = format_summary(self._stats(), "2026-04-16")
        assert "22" in result

    def test_cap_hit_note_absent_when_no_cap(self):
        result = format_summary(self._stats(), "2026-04-16")
        assert "CAP" not in result

    def test_cap_hit_note_present_when_capped(self):
        stats = parse_log_text(SAMPLE_LOG_WITH_CAP)
        result = format_summary(stats, "2026-04-16")
        assert "CAP" in result

    def test_error_note_present_when_errors(self):
        stats = parse_log_text(SAMPLE_LOG_WITH_ERRORS)
        result = format_summary(stats, "2026-04-16")
        assert "2" in result

    def test_location_filter_line_when_nonzero(self):
        result = format_summary(self._stats(), "2026-04-16")
        assert "28" in result

    def test_location_filter_line_absent_when_zero(self):
        stats = parse_log_text(SAMPLE_LOG_WITH_CAP)
        result = format_summary(stats, "2026-04-16")
        assert "non-local" not in result

    def test_cost_estimate_present(self):
        result = format_summary(self._stats(), "2026-04-16")
        assert "$" in result
