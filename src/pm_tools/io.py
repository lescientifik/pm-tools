"""Shared I/O utilities for JSONL processing and argument parsing."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from typing import IO


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
