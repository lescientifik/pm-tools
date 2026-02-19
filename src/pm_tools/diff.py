"""pm diff: Compare two JSONL files by PMID."""

from __future__ import annotations

import json
import sys
from typing import Any


def diff_jsonl(
    old_articles: list[dict[str, Any]],
    new_articles: list[dict[str, Any]],
    ignore_fields: list[str] | None = None,
) -> list[dict[str, Any]]:
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

    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []

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
    """Load JSONL file, skipping malformed lines.

    Args:
        filepath: Path to JSONL file, or "-" for stdin.

    Returns:
        List of parsed dictionaries.
    """
    articles = []
    if filepath == "-":
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "pmid" in obj:
                    articles.append(obj)
            except json.JSONDecodeError:
                continue
    else:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and "pmid" in obj:
                        articles.append(obj)
                except json.JSONDecodeError:
                    continue

    return articles


HELP_TEXT = """\
pm diff - Compare two JSONL files by PMID

Usage: pm diff [OPTIONS] OLD_FILE NEW_FILE
       pm diff [OPTIONS] OLD_FILE - < new.jsonl
       pm diff [OPTIONS] - NEW_FILE < old.jsonl

Arguments:
  OLD_FILE    Baseline/reference JSONL file (or - for stdin)
  NEW_FILE    New/comparison JSONL file (or - for stdin)
  Note: At most one of OLD_FILE or NEW_FILE can be - (stdin)

Output: Streaming JSONL with one line per difference:
  {"pmid":"...","status":"added","article":{...}}
  {"pmid":"...","status":"removed","article":{...}}
  {"pmid":"...","status":"changed","old":{...},"new":{...}}

Options:
  -q, --quiet         Suppress output, just set exit code
  --ignore FIELDS     Ignore these fields when comparing (comma-separated)
  -h, --help          Show this help

Exit Codes:
  0    No differences (files are identical)
  1    Differences found
  2    Error (invalid arguments, file not found, malformed JSON)

Examples:
  pm diff baseline_v1.jsonl baseline_v2.jsonl
  pm diff old.jsonl new.jsonl | jq -r 'select(.status=="added") | .pmid'
  pm diff file1.jsonl file2.jsonl --quiet && echo "identical"
  pm diff old.jsonl new.jsonl --ignore abstract"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm diff."""
    if args is None:
        args = sys.argv[1:]

    quiet = False
    ignore_fields: list[str] = []
    positional: list[str] = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg in ("--quiet", "-q"):
            quiet = True
        elif arg == "--ignore":
            i += 1
            if i >= len(args):
                print("Error: --ignore requires an argument", file=sys.stderr)
                return 2
            ignore_fields = [f.strip() for f in args[i].split(",")]
        elif arg.startswith("--ignore="):
            ignore_fields = [f.strip() for f in arg.split("=", 1)[1].split(",")]
        elif arg == "-":
            positional.append("-")
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            return 2
        else:
            positional.append(arg)
        i += 1

    if len(positional) < 2:
        print("Error: Two files required", file=sys.stderr)
        print("Usage: pm diff [OPTIONS] OLD_FILE NEW_FILE", file=sys.stderr)
        return 2

    if len(positional) > 2:
        print("Error: Too many arguments", file=sys.stderr)
        return 2

    old_file, new_file = positional

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

    if not quiet:
        for diff in diffs:
            print(json.dumps(diff, ensure_ascii=False))

    return 1 if diffs else 0
