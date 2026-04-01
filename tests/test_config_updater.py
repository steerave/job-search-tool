"""Tests for config_updater — asymmetric add/remove rules and YAML writing."""

import json
from unittest.mock import MagicMock
from feedback_reader import parse_tracker_feedback, parse_status_rows
from config_updater import (
    build_config_prompt,
    parse_config_suggestions,
    apply_config_updates,
    log_config_changes,
    generate_config_suggestions,
)


class TestBuildConfigPrompt:
    """build_config_prompt assembles the prompt with asymmetric rules."""

    def test_includes_current_config(self, sample_tracker_rows, sample_status_rows, sample_config):
        tracker = parse_tracker_feedback(sample_tracker_rows)
        status = parse_status_rows(sample_status_rows)
        prompt = build_config_prompt(tracker, status, sample_config)
        assert "Senior Director Digital Delivery" in prompt
        assert "ADDING" in prompt
        assert "REMOVING" in prompt

    def test_includes_asymmetric_rules(self, sample_tracker_rows, sample_status_rows, sample_config):
        tracker = parse_tracker_feedback(sample_tracker_rows)
        status = parse_status_rows(sample_status_rows)
        prompt = build_config_prompt(tracker, status, sample_config)
        assert "NEVER suggest removing required_keywords" in prompt
        assert "explicitly requests exclusion" in prompt


class TestParseConfigSuggestions:
    """parse_config_suggestions handles Claude's JSON response."""

    def test_parses_valid_json(self):
        raw = json.dumps({
            "add_job_titles": ["Director of AI Implementation"],
            "add_required_keywords": ["AI platform"],
            "reasoning": {
                "Director of AI Implementation": "User applied to 2 AI roles"
            }
        })
        result = parse_config_suggestions(raw)
        assert result["add_job_titles"] == ["Director of AI Implementation"]
        assert result["add_required_keywords"] == ["AI platform"]

    def test_handles_empty_response(self):
        result = parse_config_suggestions("{}")
        assert result.get("add_job_titles", []) == []
        assert result.get("remove_job_titles", []) == []

    def test_handles_json_in_code_block(self):
        raw = '```json\n{"add_job_titles": ["New Title"]}\n```'
        result = parse_config_suggestions(raw)
        assert result["add_job_titles"] == ["New Title"]

    def test_returns_empty_on_invalid_json(self):
        result = parse_config_suggestions("not json at all")
        assert result == {}


class TestApplyConfigUpdates:
    """apply_config_updates modifies config.yaml correctly."""

    def test_adds_new_job_title(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "job_titles:\n  - \"Director Digital Delivery\"\n\n"
            "required_keywords:\n  - \"delivery\"\n\n"
            "exclude_keywords:\n  - \"supply chain\"\n"
        )
        suggestions = {"add_job_titles": ["Director of AI Implementation"]}
        changes = apply_config_updates(str(config_file), suggestions)
        assert len(changes) == 1
        assert "Director of AI Implementation" in changes[0]

        content = config_file.read_text()
        assert "Director of AI Implementation" in content
        assert "Director Digital Delivery" in content

    def test_adds_required_keyword(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "job_titles:\n  - \"Director\"\n\n"
            "required_keywords:\n  - \"delivery\"\n\n"
            "exclude_keywords:\n  - \"supply chain\"\n"
        )
        suggestions = {"add_required_keywords": ["AI platform"]}
        changes = apply_config_updates(str(config_file), suggestions)
        assert len(changes) == 1
        content = config_file.read_text()
        assert "AI platform" in content

    def test_does_not_add_duplicate_title(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "job_titles:\n  - \"Director Digital Delivery\"\n\n"
            "required_keywords:\n  - \"delivery\"\n\n"
            "exclude_keywords:\n  - \"supply chain\"\n"
        )
        suggestions = {"add_job_titles": ["Director Digital Delivery"]}
        changes = apply_config_updates(str(config_file), suggestions)
        assert len(changes) == 0

    def test_removes_title_only_when_in_suggestions(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "job_titles:\n  - \"Director Digital Delivery\"\n  - \"Bad Title\"\n\n"
            "required_keywords:\n  - \"delivery\"\n\n"
            "exclude_keywords:\n  - \"supply chain\"\n"
        )
        suggestions = {"remove_job_titles": ["Bad Title"]}
        changes = apply_config_updates(str(config_file), suggestions)
        assert len(changes) == 1
        content = config_file.read_text()
        assert "Bad Title" not in content
        assert "Director Digital Delivery" in content

    def test_empty_suggestions_no_changes(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        original = "job_titles:\n  - \"Director\"\n\nrequired_keywords:\n  - \"delivery\"\n\nexclude_keywords:\n  - \"supply chain\"\n"
        config_file.write_text(original)
        changes = apply_config_updates(str(config_file), {})
        assert len(changes) == 0


class TestLogConfigChanges:
    """log_config_changes writes to the audit log."""

    def test_appends_to_log_file(self, tmp_path):
        log_file = tmp_path / "config_changes.log"
        changes = [
            'ADDED job_title: "Director of AI Implementation"',
            'ADDED required_keyword: "AI platform"',
        ]
        reasoning = {
            "Director of AI Implementation": "User applied to 2 AI roles",
            "AI platform": "Recurring theme in high-scored roles",
        }
        log_config_changes(str(log_file), changes, reasoning)
        content = log_file.read_text()
        assert "Director of AI Implementation" in content
        assert "User applied to 2 AI roles" in content


class TestGenerateConfigSuggestions:
    """generate_config_suggestions calls Claude and returns parsed suggestions."""

    def test_calls_claude_and_parses(self, sample_tracker_rows, sample_status_rows, sample_config):
        tracker = parse_tracker_feedback(sample_tracker_rows)
        status = parse_status_rows(sample_status_rows)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "add_job_titles": ["Director of AI Delivery"],
            "reasoning": {"Director of AI Delivery": "AI trend in applied roles"},
        }))]
        mock_client.messages.create.return_value = mock_response

        result = generate_config_suggestions(tracker, status, sample_config, mock_client)
        assert "add_job_titles" in result
        assert "Director of AI Delivery" in result["add_job_titles"]
