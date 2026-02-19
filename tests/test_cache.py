"""Tests for pm_tools.cache — cache store, audit logger, and .pm/ detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pm_tools.cache import audit_log, cache_read, cache_write, find_pm_dir

# =============================================================================
# find_pm_dir
# =============================================================================


class TestFindPmDir:
    """find_pm_dir() detects .pm/ in the current working directory."""

    def test_returns_path_when_pm_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".pm").mkdir()
        monkeypatch.chdir(tmp_path)
        result = find_pm_dir()
        assert result == tmp_path / ".pm"

    def test_returns_none_when_no_pm(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = find_pm_dir()
        assert result is None

    def test_returns_none_when_pm_is_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A .pm file (not directory) should not be detected."""
        (tmp_path / ".pm").write_text("not a directory")
        monkeypatch.chdir(tmp_path)
        result = find_pm_dir()
        assert result is None


# =============================================================================
# cache_write + cache_read
# =============================================================================


class TestCacheReadWrite:
    """Atomic cache read/write operations."""

    @pytest.fixture()
    def pm_dir(self, tmp_path: Path) -> Path:
        """Create a .pm/ structure for testing."""
        pm = tmp_path / ".pm"
        pm.mkdir()
        for sub in ("search", "fetch", "cite", "download"):
            (pm / "cache" / sub).mkdir(parents=True)
        return pm

    def test_read_missing_returns_none(self, pm_dir: Path) -> None:
        result = cache_read(pm_dir, "search", "nonexistent.json")
        assert result is None

    def test_write_then_read(self, pm_dir: Path) -> None:
        data = '{"query": "test", "count": 42}'
        cache_write(pm_dir, "search", "abc123.json", data)
        result = cache_read(pm_dir, "search", "abc123.json")
        assert result == data

    def test_write_creates_file(self, pm_dir: Path) -> None:
        cache_write(pm_dir, "fetch", "12345.xml", "<PubmedArticle/>")
        path = pm_dir / "cache" / "fetch" / "12345.xml"
        assert path.exists()

    def test_read_corrupted_json_returns_none(self, pm_dir: Path) -> None:
        """Corrupted JSON file should be treated as cache miss."""
        path = pm_dir / "cache" / "search" / "bad.json"
        path.write_text('{"truncated')
        result = cache_read(pm_dir, "search", "bad.json")
        assert result is None

    def test_read_corrupted_xml_returns_none(self, pm_dir: Path) -> None:
        """Corrupted XML file should be treated as cache miss."""
        path = pm_dir / "cache" / "fetch" / "bad.xml"
        path.write_text("<PubmedArticle><broken")
        result = cache_read(pm_dir, "fetch", "bad.xml")
        assert result is None

    def test_read_valid_cite_json(self, pm_dir: Path) -> None:
        data = '{"PMID": "12345", "title": "Test"}'
        cache_write(pm_dir, "cite", "12345.json", data)
        result = cache_read(pm_dir, "cite", "12345.json")
        assert result == data

    def test_write_overwrites_existing(self, pm_dir: Path) -> None:
        cache_write(pm_dir, "search", "key.json", '{"old": true}')
        cache_write(pm_dir, "search", "key.json", '{"new": true}')
        result = cache_read(pm_dir, "search", "key.json")
        assert result == '{"new": true}'

    def test_none_pm_dir_read_returns_none(self) -> None:
        result = cache_read(None, "search", "key.json")  # type: ignore[arg-type]
        assert result is None

    def test_none_pm_dir_write_is_noop(self) -> None:
        # Should not raise
        cache_write(None, "search", "key.json", "data")  # type: ignore[arg-type]


# =============================================================================
# audit_log
# =============================================================================


class TestAuditLog:
    """Append-only audit logger."""

    @pytest.fixture()
    def pm_dir(self, tmp_path: Path) -> Path:
        pm = tmp_path / ".pm"
        pm.mkdir()
        (pm / "audit.jsonl").write_text("")
        return pm

    def test_appends_jsonl_line(self, pm_dir: Path) -> None:
        audit_log(pm_dir, {"op": "search", "query": "test"})
        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "search"

    def test_adds_timestamp(self, pm_dir: Path) -> None:
        audit_log(pm_dir, {"op": "fetch"})
        event = json.loads((pm_dir / "audit.jsonl").read_text().strip())
        assert "ts" in event
        # ISO 8601 format check
        assert "T" in event["ts"]
        assert event["ts"].endswith("Z")

    def test_multiple_appends(self, pm_dir: Path) -> None:
        audit_log(pm_dir, {"op": "search"})
        audit_log(pm_dir, {"op": "fetch"})
        audit_log(pm_dir, {"op": "filter"})
        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 3
        ops = [json.loads(line)["op"] for line in lines]
        assert ops == ["search", "fetch", "filter"]

    def test_noop_when_pm_dir_none(self) -> None:
        # Should not raise
        audit_log(None, {"op": "test"})  # type: ignore[arg-type]

    def test_preserves_existing_content(self, pm_dir: Path) -> None:
        """Existing audit lines are not overwritten."""
        (pm_dir / "audit.jsonl").write_text('{"ts":"2026-01-01T00:00:00Z","op":"init"}\n')
        audit_log(pm_dir, {"op": "search"})
        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["op"] == "init"
        assert json.loads(lines[1])["op"] == "search"
