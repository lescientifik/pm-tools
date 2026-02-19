"""Tests for pm init — Initialize .pm/ directory with cache and audit trail."""

from __future__ import annotations

import json

import pytest

from pm_tools.init import init


class TestInitCreatesStructure:
    """pm init creates the .pm/ directory with expected structure."""

    def test_creates_pm_directory(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = init()
        assert result == 0
        assert (tmp_path / ".pm").is_dir()  # type: ignore[union-attr]

    def test_creates_cache_subdirectories(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        init()
        for subdir in ("search", "fetch", "cite", "download"):
            assert (tmp_path / ".pm" / "cache" / subdir).is_dir()  # type: ignore[union-attr]

    def test_creates_audit_jsonl(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        init()
        audit_path = tmp_path / ".pm" / "audit.jsonl"  # type: ignore[union-attr]
        assert audit_path.exists()

    def test_creates_gitignore(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        init()
        gitignore = tmp_path / ".pm" / ".gitignore"  # type: ignore[union-attr]
        assert gitignore.exists()
        content = gitignore.read_text()
        assert "cache/" in content


class TestInitAuditEvent:
    """pm init logs an init event in audit.jsonl."""

    def test_logs_init_event(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        init()
        audit_path = tmp_path / ".pm" / "audit.jsonl"  # type: ignore[union-attr]
        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "init"
        assert "ts" in event


class TestInitAlreadyExists:
    """pm init fails if .pm/ already exists."""

    def test_fails_if_pm_exists(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".pm").mkdir()  # type: ignore[union-attr]
        result = init()
        assert result == 1
        captured = capsys.readouterr()
        assert "already exists" in captured.err


class TestInitCLI:
    """pm init is accessible via the pm CLI."""

    def test_init_in_subcommands(self) -> None:
        from pm_tools.cli import SUBCOMMANDS

        assert "init" in SUBCOMMANDS
