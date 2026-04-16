"""Tests for job_scraper filtering helpers."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from job_scraper import _filter_by_location


class TestFilterByLocation:
    """_filter_by_location keeps jobs matching include patterns, drops others."""

    def _job(self, location: str) -> dict:
        return {"title": "Test Job", "company": "Acme", "location": location}

    def test_keeps_davenport_job(self):
        jobs = [self._job("Davenport, IA")]
        patterns = ["davenport", ", ia"]
        assert _filter_by_location(jobs, patterns) == jobs

    def test_keeps_moline_job(self):
        jobs = [self._job("Moline, IL")]
        patterns = ["moline", "rock island"]
        assert _filter_by_location(jobs, patterns) == jobs

    def test_keeps_empty_location(self):
        jobs = [self._job("")]
        patterns = ["davenport", ", ia"]
        assert _filter_by_location(jobs, patterns) == jobs

    def test_drops_san_francisco_job(self):
        jobs = [self._job("San Francisco, CA")]
        patterns = ["davenport", ", ia"]
        assert _filter_by_location(jobs, patterns) == []

    def test_drops_new_york_job(self):
        jobs = [self._job("New York, NY")]
        patterns = ["davenport", "moline", ", ia"]
        assert _filter_by_location(jobs, patterns) == []

    def test_empty_patterns_returns_all(self):
        jobs = [self._job("Denver, CO"), self._job("Davenport, IA")]
        assert _filter_by_location(jobs, []) == jobs

    def test_case_insensitive_match(self):
        jobs = [self._job("DAVENPORT, IA")]
        patterns = ["davenport"]
        assert _filter_by_location(jobs, patterns) == jobs

    def test_keeps_ia_state_only(self):
        """Location with just ', ia' (Iowa) is within scope."""
        jobs = [self._job("Iowa City, IA")]
        patterns = [", ia"]
        assert _filter_by_location(jobs, patterns) == jobs

    def test_mixed_batch(self):
        jobs = [
            self._job("Davenport, IA"),
            self._job("Boston, MA"),
            self._job(""),
            self._job("Moline, IL"),
            self._job("Chicago, IL"),
        ]
        patterns = ["davenport", "moline", "bettendorf", "rock island", "east moline", ", ia"]
        result = _filter_by_location(jobs, patterns)
        locations = [j["location"] for j in result]
        assert "Davenport, IA" in locations
        assert "" in locations
        assert "Moline, IL" in locations
        assert "Boston, MA" not in locations
        assert "Chicago, IL" not in locations
