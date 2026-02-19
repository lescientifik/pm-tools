"""pm_tools.cache — Cache store, audit logger, and .pm/ directory utilities."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


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


def audit_log(pm_dir: Path | None, event: dict) -> None:
    """Append a single JSON event to .pm/audit.jsonl atomically.

    Uses O_APPEND + single os.write() for POSIX atomicity (< PIPE_BUF).

    Args:
        pm_dir: Path to .pm/ directory, or None (no-op).
        event: Event dict. A 'ts' field is added automatically.
    """
    if pm_dir is None:
        return

    event["ts"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = json.dumps(event, ensure_ascii=False) + "\n"
    data = line.encode("utf-8")

    audit_path = pm_dir / "audit.jsonl"
    fd = os.open(str(audit_path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
