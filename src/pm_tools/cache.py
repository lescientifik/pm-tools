"""pm_tools.cache — Cache store, audit logger, and .pm/ directory utilities."""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pm_tools.io import validate_filename_safe


def find_pm_dir() -> Path | None:
    """Detect .pm/ directory in the current working directory.

    Returns:
        Path to .pm/ if it exists and is a directory, None otherwise.
    """
    pm = Path.cwd() / ".pm"
    if pm.is_dir():
        return pm
    return None


# =============================================================================
# Cache store — atomic read/write
# =============================================================================

# Categories that store JSON (validated on read)
_JSON_CATEGORIES = {"search", "cite", "download"}
# Categories that store XML (validated on read)
_XML_CATEGORIES = {"fetch"}


def cache_read(pm_dir: Path | None, category: str, key: str) -> str | None:
    """Read a cached value. Returns None on miss or corruption.

    Args:
        pm_dir: Path to .pm/ directory, or None (returns None).
        category: Cache category (search, fetch, cite, download).
        key: Cache key (filename).

    Returns:
        Cached data as string, or None if not found/corrupted.
    """
    if pm_dir is None:
        return None

    path = pm_dir / "cache" / category / key
    if not path.exists():
        return None

    try:
        data = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Validate content based on category
    try:
        if category in _JSON_CATEGORIES:
            json.loads(data)
        elif category in _XML_CATEGORIES:
            ET.fromstring(data)
    except (json.JSONDecodeError, ET.ParseError):
        return None

    return data


def cache_write(pm_dir: Path | None, category: str, key: str, data: str) -> None:
    """Write data to cache atomically (write-to-temp + os.replace).

    Args:
        pm_dir: Path to .pm/ directory, or None (no-op).
        category: Cache category (search, fetch, cite, download).
        key: Cache key (filename).
        data: Data to cache.
    """
    if pm_dir is None:
        return

    # Defense in depth: validate the key before using it in a path.


    validate_filename_safe(key)

    path = pm_dir / "cache" / category / key
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: temp file + rename
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, data.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


# =============================================================================
# Audit logger — atomic append
# =============================================================================


def audit_log(pm_dir: Path | None, event: dict[str, Any]) -> None:
    """Append a single JSON event to .pm/audit.jsonl atomically.

    Uses O_APPEND + single os.write() for POSIX atomicity (< PIPE_BUF).

    Args:
        pm_dir: Path to .pm/ directory, or None (no-op).
        event: Event dict. A 'ts' field is added automatically.
    """
    if pm_dir is None:
        return

    event = {**event, "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    line = json.dumps(event, ensure_ascii=False) + "\n"
    data = line.encode("utf-8")

    audit_path = pm_dir / "audit.jsonl"
    fd = os.open(str(audit_path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


# =============================================================================
# Generic cache-aware batch fetcher
# =============================================================================


def cached_batch_fetch(
    ids: list[str],
    *,
    pm_dir: Path | None,
    cache_category: str,
    cache_ext: str,
    fetch_batch: Callable[[list[str]], list[tuple[str, str]]],
    batch_size: int = 200,
    rate_limit_delay: float = 0.34,
    refresh: bool = False,
    verbose: bool = False,
    deduplicate: bool = False,
) -> dict[str, str]:
    """Fetch data for IDs with caching, batching, rate limiting, and audit logging.

    This is the shared core used by fetch() and cite(). The actual HTTP call
    and response parsing is delegated to the ``fetch_batch`` callback.

    Args:
        ids: List of ID strings to fetch.
        pm_dir: Path to .pm/ directory for caching/audit, or None.
        cache_category: Cache subdirectory name (e.g. "fetch", "cite").
        cache_ext: File extension for cache files (e.g. ".xml", ".json").
        fetch_batch: Callback that takes a list of IDs and returns
            ``list[tuple[str, str]]`` of (id, data) pairs.
        batch_size: Max IDs per fetch_batch call.
        rate_limit_delay: Seconds to sleep between batches.
        refresh: If True, bypass cache and re-fetch everything.
        verbose: If True, print progress to stderr.
        deduplicate: If True, remove duplicate IDs before processing.

    Returns:
        Dict mapping each ID to its data string (from cache or fetch).
    """
    if not ids:
        return {}

    # Deduplicate if requested
    if deduplicate:
        seen: set[str] = set()
        unique: list[str] = []
        for id_ in ids:
            if id_ not in seen:
                seen.add(id_)
                unique.append(id_)
        ids = unique

    # Split into cached / uncached
    cached: dict[str, str] = {}
    uncached: list[str] = []

    if pm_dir is not None and not refresh:
        for id_ in ids:
            hit = cache_read(pm_dir, cache_category, f"{id_}{cache_ext}")
            if hit is not None:
                cached[id_] = hit
            else:
                uncached.append(id_)
    else:
        uncached = list(ids)

    # Batch-fetch uncached IDs
    fetched: dict[str, str] = {}
    for batch_num, i in enumerate(range(0, len(uncached), batch_size)):
        batch = uncached[i : i + batch_size]

        if batch_num > 0 and rate_limit_delay > 0:
            time.sleep(rate_limit_delay)

        if verbose:
            print(
                f"Fetching batch {batch_num + 1} ({len(batch)} IDs)...",
                file=sys.stderr,
            )

        pairs = fetch_batch(batch)
        for id_, data in pairs:
            fetched[id_] = data
            cache_write(pm_dir, cache_category, f"{id_}{cache_ext}", data)

    # Audit log
    audit_log(
        pm_dir,
        {
            "op": cache_category,
            "requested": len(ids),
            "cached": len(cached),
            "fetched": len(fetched),
            "refreshed": refresh,
        },
    )

    # Merge cached + fetched, preserving original ID order.
    # Also include any fetched IDs not in the original list (e.g. when the
    # fetch_batch callback discovers IDs from the response payload).
    result: dict[str, str] = {}
    for id_ in ids:
        if id_ in cached:
            result[id_] = cached[id_]
        elif id_ in fetched:
            result[id_] = fetched[id_]
    # Append any extra IDs returned by fetch_batch but not in the input list
    for id_, data in fetched.items():
        if id_ not in result:
            result[id_] = data

    return result
