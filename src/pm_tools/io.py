"""Shared I/O utilities for JSONL processing, input validation, and argument parsing."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Iterator
from typing import IO

logger = logging.getLogger(__name__)


def safe_parse(
    parser: argparse.ArgumentParser,
    args: list[str] | None,
) -> tuple[argparse.Namespace | None, int | None]:
    """Parse *args* with *parser*, catching ``SystemExit`` from argparse.

    Returns ``(namespace, None)`` on success, or ``(None, exit_code)`` when
    argparse calls ``sys.exit`` (--help, errors, etc.).
    """
    try:
        ns = parser.parse_args(args)
    except SystemExit as e:
        return None, int(e.code) if e.code is not None else 0
    return ns, None


def read_jsonl(stream: IO[str]) -> Iterator[dict]:
    """Read JSONL from a stream, yielding dicts.

    Skips blank lines, malformed JSON, and non-dict values.
    Emits a warning for malformed JSON lines.
    """
    for n, line in enumerate(stream, 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("skipping malformed JSON on line %d", n)
            continue
        if isinstance(obj, dict):
            yield obj


# ---------------------------------------------------------------------------
# Input validation — two-tier strategy
# ---------------------------------------------------------------------------

_PMID_RE = re.compile(r"^\d+$")
_FILENAME_SAFE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_pmid(value: str) -> str:
    """Validate that *value* is a strictly numeric PMID (for E-utilities).

    Returns the value unchanged on success. Raises ``ValueError`` if the
    string is empty, contains non-digit characters, or embeds null bytes.
    """
    if not _PMID_RE.match(value):
        msg = f"Invalid PMID: {value!r} (must be numeric)"
        raise ValueError(msg)
    return value


def validate_filename_safe(value: str) -> str:
    """Validate that *value* is safe for use as a filename component.

    Accepts alphanumerics, dots, hyphens, and underscores — enough for
    PMIDs (``12345678``) and PMC IDs (``PMC1234567``). Rejects slashes,
    backslashes, null bytes, and any other path-manipulation characters.

    Returns the value unchanged on success.
    """
    if not _FILENAME_SAFE_RE.match(value):
        msg = f"Identifier {value!r} is not filename-safe"
        raise ValueError(msg)
    return value
