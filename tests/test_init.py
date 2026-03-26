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


class TestInitIdempotent:
    """pm init is idempotent — succeeds even if .pm/ already exists."""

    def test_returns_zero_when_already_initialized(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Calling init() twice returns 0 both times."""
        monkeypatch.chdir(tmp_path)
        assert init() == 0
        assert init() == 0

    def test_stderr_says_already_initialized(
        self,
        tmp_path: object,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Second call prints 'already initialized' (not 'Error:') on stderr."""
        monkeypatch.chdir(tmp_path)
        init()
        capsys.readouterr()  # discard first-call output
        init()
        captured = capsys.readouterr()
        assert "already initialized" in captured.err
        assert "Error:" not in captured.err

    def test_first_call_still_creates_everything(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First call creates the full .pm/ structure as before."""
        monkeypatch.chdir(tmp_path)
        init()
        assert (tmp_path / ".pm" / "audit.jsonl").exists()  # type: ignore[union-attr]
        assert (tmp_path / ".pm" / "cache" / "search").is_dir()  # type: ignore[union-attr]
        assert (tmp_path / ".pm" / ".gitignore").exists()  # type: ignore[union-attr]

    def test_pm_as_file_returns_error(
        self,
        tmp_path: object,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """If .pm exists as a regular file (not a directory), return 1."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".pm").write_text("oops")  # type: ignore[union-attr]
        assert init() == 1
        captured = capsys.readouterr()
        assert "not a directory" in captured.err


class TestInitCLI:
    """pm init is accessible via the pm CLI."""

    def test_help_returns_zero(self) -> None:
        from pm_tools.init import main

        assert main(["--help"]) == 0

    def test_unknown_option_returns_two(self) -> None:
        from pm_tools.init import main

        assert main(["--unknown"]) == 2
