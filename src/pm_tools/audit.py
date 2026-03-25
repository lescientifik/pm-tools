"""pm audit: View audit trail and generate PRISMA reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pm_tools.cache import find_pm_dir
from pm_tools.io import safe_parse
from pm_tools.types import AuditEvent


def _read_events(pm_dir: Path) -> list[AuditEvent]:
    """Read all valid events from audit.jsonl, skipping corrupted lines."""
    audit_path = pm_dir / "audit.jsonl"
    if not audit_path.exists():
        return []

    events: list[AuditEvent] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def audit_summary(pm_dir: Path) -> dict[str, Any]:
    """Generate summary of all operations in the audit trail.

    Returns:
        Dict with total_events count and by_op breakdown.
    """
    events = _read_events(pm_dir)
    by_op: dict[str, int] = {}
    for event in events:
        op = event.get("op", "unknown")
        by_op[op] = by_op.get(op, 0) + 1

    return {
        "total_events": len(events),
        "by_op": by_op,
    }


def audit_searches(pm_dir: Path) -> list[AuditEvent]:
    """List all search operations from the audit trail.

    Returns:
        List of search event dicts (query, count, ts, cached).
    """
    events = _read_events(pm_dir)
    return [e for e in events if e.get("op") == "search"]


def _format_summary(summary: dict[str, Any]) -> str:
    """Format audit summary for display."""
    lines = ["Audit Trail Summary", "===================", ""]
    if summary["total_events"] == 0:
        lines.append("No operations recorded.")
        return "\n".join(lines)

    lines.append(f"Total operations: {summary['total_events']}")
    lines.append("")
    for op, count in sorted(summary["by_op"].items()):
        lines.append(f"  {op:12s} {count:>5d}")
    return "\n".join(lines)


def _format_searches(searches: list[dict[str, Any]]) -> str:
    """Format search list for display."""
    lines = ["Search History", "=============", ""]
    if not searches:
        lines.append("No searches recorded.")
        return "\n".join(lines)

    for s in searches:
        query = s.get("query", "?")
        count = s.get("count", "?")
        ts = s.get("ts", "?")
        cached = s.get("cached", False)
        cache_marker = " (cached)" if cached else ""
        lines.append(f'  [{ts[:10]}] "{query}" → {count} PMIDs{cache_marker}')
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for pm audit."""
    parser = argparse.ArgumentParser(
        prog="pm audit",
        description="View audit trail and PRISMA report.",
    )
    parser.add_argument("--searches", action="store_true", help="List all search operations")
    return parser


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm audit."""
    if args is None:
        args = sys.argv[1:]

    parser = _build_parser()
    parsed, code = safe_parse(parser, args)
    if parsed is None:
        return code  # type: ignore[return-value]

    show_searches: bool = parsed.searches

    pm_dir = find_pm_dir()
    if pm_dir is None:
        print(
            "Error: No .pm/ directory found. Run 'pm init' first.",
            file=sys.stderr,
        )
        return 1

    if show_searches:
        searches = audit_searches(pm_dir)
        print(_format_searches(searches))
    else:
        summary = audit_summary(pm_dir)
        print(_format_summary(summary))

    return 0
