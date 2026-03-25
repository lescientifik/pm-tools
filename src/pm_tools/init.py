"""pm init: Initialize .pm/ directory with cache and audit trail."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from pm_tools.io import safe_parse

PM_DIR = ".pm"
CACHE_SUBDIRS = ("search", "fetch", "cite", "download")

GITIGNORE_CONTENT = "cache/\n"


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for pm init."""
    parser = argparse.ArgumentParser(
        prog="pm init",
        description=(
            "Initialize audit trail and cache for the current directory.\n\n"
            "Creates a .pm/ directory with:\n"
            "  - audit.jsonl  : append-only log of all pm operations (git-trackable)\n"
            "  - cache/       : local cache of API responses (gitignored)\n\n"
            "Use 'pm audit' to view the audit trail."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    return parser


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

    parser = _build_parser()
    _, code = safe_parse(parser, args)
    if code is not None:
        return code

    return init()
