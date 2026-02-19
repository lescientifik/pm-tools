"""pm init: Initialize .pm/ directory with cache and audit trail."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PM_DIR = ".pm"
CACHE_SUBDIRS = ("search", "fetch", "cite", "download")

GITIGNORE_CONTENT = "cache/\n"

HELP_TEXT = """\
pm init - Initialize audit trail and cache for the current directory

Usage: pm init

Creates a .pm/ directory with:
  - audit.jsonl  : append-only log of all pm operations (git-trackable)
  - cache/       : local cache of API responses (gitignored)

Use 'pm audit' to view the audit trail."""


def init() -> int:
    """Create .pm/ directory structure in the current working directory.

    Returns:
        0 on success, 1 if .pm/ already exists.
    """
    pm_path = Path.cwd() / PM_DIR

    # Use os.mkdir for atomicity — fails if directory exists
    try:
        os.mkdir(pm_path)
    except FileExistsError:
        print(f"Error: {PM_DIR}/ already exists in {Path.cwd()}", file=sys.stderr)
        return 1

    # Create cache subdirectories
    cache_dir = pm_path / "cache"
    cache_dir.mkdir()
    for subdir in CACHE_SUBDIRS:
        (cache_dir / subdir).mkdir()

    # Create .gitignore
    (pm_path / ".gitignore").write_text(GITIGNORE_CONTENT)

    # Create audit.jsonl with init event
    event = {
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "op": "init",
    }
    audit_path = pm_path / "audit.jsonl"
    audit_path.write_text(json.dumps(event, ensure_ascii=False) + "\n")

    print(f"Initialized {PM_DIR}/ in {Path.cwd()}")
    print(f"Audit trail: {PM_DIR}/audit.jsonl")
    print(f"Cache: {PM_DIR}/cache/")

    return 0


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm init."""
    if args is None:
        args = sys.argv[1:]

    for arg in args:
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            return 2

    return init()
