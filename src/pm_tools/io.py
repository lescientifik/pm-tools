"""Shared I/O utilities for JSONL processing and input validation."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import IO


def read_jsonl(stream: IO[str]) -> Iterator[dict]:
    """Read JSONL from a stream, yielding dicts.

    Skips blank lines, malformed JSON, and non-dict values.
    """
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_FILENAME_SAFE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_filename_safe(value: str) -> str:
    """Validate that *value* is safe for use as a filename component.

    Accepts alphanumerics, dots, hyphens, and underscores -- enough for
    PMIDs (``12345678``) and PMC IDs (``PMC1234567``). Rejects slashes,
    backslashes, null bytes, and any other path-manipulation characters.

    Returns the value unchanged on success.

    Raises:
        ValueError: If the value contains unsafe characters.
    """
    if not _FILENAME_SAFE_RE.match(value):
        msg = f"Identifier {value!r} is not filename-safe"
        raise ValueError(msg)
    return value
