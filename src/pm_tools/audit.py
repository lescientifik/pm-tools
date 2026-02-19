"""pm audit: View audit trail and generate PRISMA reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _read_events(pm_dir: Path) -> list[dict[str, Any]]:
    """Read all valid events from audit.jsonl, skipping corrupted lines."""
    audit_path = pm_dir / "audit.jsonl"
    if not audit_path.exists():
        return []

    events: list[dict[str, Any]] = []
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


def audit_searches(pm_dir: Path) -> list[dict[str, Any]]:
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


HELP_TEXT = """\
pm audit - View audit trail and PRISMA report

Usage: pm audit [OPTIONS]

Options:
  --searches    List all search operations with dates and counts
  -h, --help    Show this help message

Output:
  Human-readable audit summary to stdout

Examples:
  pm audit                # Summary of all operations
  pm audit --searches     # List of searches with dates"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm audit."""
    if args is None:
        args = sys.argv[1:]

    show_searches = False

    for arg in args:
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg == "--searches":
            show_searches = True
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            return 2

    from pm_tools.cache import find_pm_dir

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
