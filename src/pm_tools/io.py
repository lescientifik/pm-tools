"""Shared I/O utilities for JSONL processing, input validation, and argument parsing."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Iterable, Iterator
from typing import IO, Literal

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


# ---------------------------------------------------------------------------
# JSONL stdin auto-detection — shared by fetch, cite, download
# ---------------------------------------------------------------------------


def detect_input_format(first_line: str) -> Literal["jsonl", "plain"]:
    """Detect whether input lines are JSONL or plain PMIDs from first non-empty line.

    Returns ``"jsonl"`` if the line parses as a JSON dict, ``"plain"`` otherwise.
    Strips whitespace before attempting to parse.
    """
    stripped = first_line.strip()
    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return "plain"
    if isinstance(obj, dict):
        return "jsonl"
    return "plain"


def read_pmids_from_lines(lines: Iterable[str]) -> list[str]:
    """Extract PMIDs from lines that may be plain PMIDs or JSONL.

    Auto-detects format from first non-empty line (strips whitespace before parsing):
    - If it parses as a JSON dict -> JSONL mode, extract ``pmid`` from each line
    - Otherwise -> plain PMID mode (one PMID per line, stripped)

    Returns a list of PMID strings (not validated -- caller validates).
    Emits a warning if JSONL is detected but a line has no ``pmid`` field.
    """
    max_pmids = 100_000
    result: list[str] = []
    fmt: Literal["jsonl", "plain"] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if len(result) >= max_pmids:
            logger.warning("input truncated at %d PMIDs", max_pmids)
            break

        # Detect format on the first non-empty line
        if fmt is None:
            fmt = detect_input_format(stripped)

        if fmt == "plain":
            result.append(stripped)
        else:
            # JSONL mode
            try:
                obj = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                logger.warning("skipping malformed JSON line: %.200s", stripped)
                continue
            if isinstance(obj, dict):
                pmid = obj.get("pmid")
                if isinstance(pmid, (str, int)):
                    result.append(str(pmid))
                elif pmid is not None:
                    logger.warning(
                        "JSONL 'pmid' field has unexpected type %s, skipping",
                        type(pmid).__name__,
                    )
                else:
                    logger.warning(
                        "JSONL line has no 'pmid' field, skipping: %.200s",
                        stripped,
                    )
            else:
                logger.warning("skipping non-dict JSON value: %.200s", stripped)

    return result
