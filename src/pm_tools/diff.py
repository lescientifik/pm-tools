"""pm diff: Compare two JSONL files by PMID."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from pm_tools.io import read_jsonl
from pm_tools.types import DiffResult


def diff_jsonl(
    old_articles: list[dict[str, Any]],
    new_articles: list[dict[str, Any]],
    ignore_fields: list[str] | None = None,
) -> list[DiffResult]:
    """Compare two lists of articles by PMID.

    Args:
        old_articles: Baseline articles.
        new_articles: New/comparison articles.
        ignore_fields: Fields to ignore when comparing.

    Returns:
        List of difference records with:
        - {"pmid": ..., "status": "added", "article": {...}}
        - {"pmid": ..., "status": "removed", "article": {...}}
        - {"pmid": ..., "status": "changed", "old": {...}, "new": {...}}
    """
    ignore = set(ignore_fields) if ignore_fields else set()

    # Build lookup by PMID (last occurrence wins for duplicates, skip non-dicts)
    old_by_pmid: dict[str, dict] = {}
    for article in old_articles:
        if not isinstance(article, dict):
            continue
        pmid = article.get("pmid")
        if pmid:
            old_by_pmid[pmid] = article

    new_by_pmid: dict[str, dict] = {}
    for article in new_articles:
        if not isinstance(article, dict):
            continue
        pmid = article.get("pmid")
        if pmid:
            new_by_pmid[pmid] = article

    removed: list[DiffResult] = []
    changed: list[DiffResult] = []
    added: list[DiffResult] = []

    # Find removed and changed
    for pmid, old_article in old_by_pmid.items():
        if pmid not in new_by_pmid:
            removed.append(
                {
                    "pmid": pmid,
                    "status": "removed",
                    "article": old_article,
                }
            )
        else:
            new_article = new_by_pmid[pmid]
            # Compare after removing ignored fields
            old_cmp = {k: v for k, v in old_article.items() if k not in ignore}
            new_cmp = {k: v for k, v in new_article.items() if k not in ignore}
            if old_cmp != new_cmp:
                # Identify which fields changed
                all_keys = set(old_cmp.keys()) | set(new_cmp.keys())
                changed_fields = sorted(k for k in all_keys if old_cmp.get(k) != new_cmp.get(k))
                changed.append(
                    {
                        "pmid": pmid,
                        "status": "changed",
                        "old": old_article,
                        "new": new_article,
                        "changed_fields": changed_fields,
                    }
                )

    # Find added
    for pmid, new_article in new_by_pmid.items():
        if pmid not in old_by_pmid:
            added.append(
                {
                    "pmid": pmid,
                    "status": "added",
                    "article": new_article,
                }
            )

    # Order: removed → changed → added
    return removed + changed + added


def diff_summary(
    old_articles: list[dict[str, Any]],
    new_articles: list[dict[str, Any]],
    ignore_fields: list[str] | None = None,
) -> dict[str, int]:
    """Return aggregate diff statistics.

    Returns:
        Dict with added, removed, changed, unchanged counts.
    """
    diffs = diff_jsonl(old_articles, new_articles, ignore_fields)

    old_by_pmid = {a["pmid"] for a in old_articles if isinstance(a, dict) and "pmid" in a}
    new_by_pmid = {a["pmid"] for a in new_articles if isinstance(a, dict) and "pmid" in a}

    added_count = sum(1 for d in diffs if d["status"] == "added")
    removed_count = sum(1 for d in diffs if d["status"] == "removed")
    changed_count = sum(1 for d in diffs if d["status"] == "changed")
    unchanged_count = len(old_by_pmid & new_by_pmid) - changed_count

    return {
        "added": added_count,
        "removed": removed_count,
        "changed": changed_count,
        "unchanged": unchanged_count,
    }


def load_jsonl(filepath: str) -> list[dict[str, Any]]:
    """Load JSONL file, skipping malformed lines and non-dict values.

    Only keeps dicts that contain a "pmid" key (required for diff).

    Args:
        filepath: Path to JSONL file, or "-" for stdin.

    Returns:
        List of parsed dictionaries.
    """
    if filepath == "-":
        return [obj for obj in read_jsonl(sys.stdin) if "pmid" in obj]
    else:
        with open(filepath) as f:
            return [obj for obj in read_jsonl(f) if "pmid" in obj]


def _build_parser() -> argparse.ArgumentParser:
    """Build argument parser for pm diff."""
    parser = argparse.ArgumentParser(
        prog="pm diff",
        description="Compare two JSONL files by PMID.",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress output, just set exit code"
    )
    parser.add_argument("--ignore", default="", help="Ignore these fields (comma-separated)")
    parser.add_argument("old_file", metavar="OLD_FILE", help="Baseline JSONL file (or - for stdin)")
    parser.add_argument("new_file", metavar="NEW_FILE", help="New JSONL file (or - for stdin)")
    return parser


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm diff."""
    if args is None:
        args = sys.argv[1:]

    parser = _build_parser()
    try:
        parsed = parser.parse_args(args)
    except SystemExit as e:
        return 2 if e.code != 0 else 0

    ignore_fields = [f.strip() for f in parsed.ignore.split(",") if f.strip()]
    old_file: str = parsed.old_file
    new_file: str = parsed.new_file

    if old_file == "-" and new_file == "-":
        print("Error: Cannot use stdin (-) for both files", file=sys.stderr)
        return 2

    # Validate files exist
    import os

    if old_file != "-" and not os.path.isfile(old_file):
        print(f"Error: File does not exist: {old_file}", file=sys.stderr)
        return 2
    if new_file != "-" and not os.path.isfile(new_file):
        print(f"Error: File does not exist: {new_file}", file=sys.stderr)
        return 2

    old_articles = load_jsonl(old_file)
    new_articles = load_jsonl(new_file)

    diffs = diff_jsonl(old_articles, new_articles, ignore_fields or None)

    if not parsed.quiet:
        for diff in diffs:
            print(json.dumps(diff, ensure_ascii=False))

    return 1 if diffs else 0
