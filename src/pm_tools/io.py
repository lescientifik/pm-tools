"""Shared I/O utilities for JSONL processing."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from typing import IO


def safe_parse(parser: argparse.ArgumentParser, args: list[str]) -> argparse.Namespace | int:
    """Parse arguments, returning Namespace on success or exit code on failure.

    Wraps ``parser.parse_args`` so callers don't need a raw
    ``try/except SystemExit`` block.

    Returns:
        Parsed ``argparse.Namespace`` on success, or an ``int`` exit code
        (0 for ``--help``, 2 for errors).
    """
    try:
        return parser.parse_args(args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0


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
