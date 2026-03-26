"""Tests for pm_tools.audit — pm audit command for viewing audit trail."""

from __future__ import annotations

import json
from pathlib import Path

from pm_tools.audit import audit_searches, audit_summary


def _write_events(pm_dir: Path, events: list[dict]) -> None:
    lines = []
    for event in events:
        lines.append(json.dumps(event))
    (pm_dir / "audit.jsonl").write_text("\n".join(lines) + "\n")


class TestAuditSummary:
    """pm audit (no flags) shows operation summary."""

    def test_empty_audit_returns_no_operations(self, pm_dir: Path) -> None:
        result = audit_summary(pm_dir)
        assert result["total_events"] == 0

    def test_counts_operations_by_type(self, pm_dir: Path) -> None:
        _write_events(
            pm_dir,
            [
                {"op": "search", "query": "CRISPR", "count": 100, "ts": "2026-02-19T10:00:00Z"},
                {"op": "search", "query": "gene", "count": 50, "ts": "2026-02-19T10:01:00Z"},
                {
                    "op": "fetch",
                    "requested": 150,
                    "cached": 0,
                    "fetched": 150,
                    "ts": "2026-02-19T10:02:00Z",
                },
                {
                    "op": "filter",
                    "input": 150,
                    "output": 80,
                    "excluded": 70,
                    "ts": "2026-02-19T10:03:00Z",
                },
            ],
        )
        result = audit_summary(pm_dir)
        assert result["total_events"] == 4
        assert result["by_op"]["search"] == 2
        assert result["by_op"]["fetch"] == 1
        assert result["by_op"]["filter"] == 1

    def test_ignores_corrupted_lines(self, pm_dir: Path) -> None:
        (pm_dir / "audit.jsonl").write_text(
            '{"op": "search", "ts": "2026-02-19T10:00:00Z"}\n'
            "this is not json\n"
            '{"op": "fetch", "ts": "2026-02-19T10:01:00Z"}\n'
        )
        result = audit_summary(pm_dir)
        assert result["total_events"] == 2


class TestAuditSearches:
    """pm audit --searches lists all search operations."""

    def test_lists_searches_with_dates(self, pm_dir: Path) -> None:
        _write_events(
            pm_dir,
            [
                {
                    "op": "search",
                    "query": "CRISPR cancer",
                    "count": 100,
                    "cached": False,
                    "ts": "2026-02-19T10:00:00Z",
                },
                {
                    "op": "fetch",
                    "requested": 100,
                    "ts": "2026-02-19T10:01:00Z",
                },
                {
                    "op": "search",
                    "query": "gene therapy",
                    "count": 50,
                    "cached": False,
                    "ts": "2026-02-19T10:02:00Z",
                },
            ],
        )
        searches = audit_searches(pm_dir)
        assert len(searches) == 2
        assert searches[0]["query"] == "CRISPR cancer"
        assert searches[0]["count"] == 100
        assert searches[1]["query"] == "gene therapy"

    def test_empty_audit_returns_empty_list(self, pm_dir: Path) -> None:
        searches = audit_searches(pm_dir)
        assert searches == []


