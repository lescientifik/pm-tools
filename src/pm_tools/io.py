"""Shared I/O utilities for JSONL processing."""

from __future__ import annotations

import json
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
