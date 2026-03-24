"""Tests for pm_tools.io — shared JSONL utilities."""

from __future__ import annotations

import io

from pm_tools.io import read_jsonl


def test_valid_jsonl_yields_dicts() -> None:
    """Valid JSONL lines with dict objects are yielded."""
    stream = io.StringIO('{"pmid": "1", "title": "A"}\n{"pmid": "2", "title": "B"}\n')
    result = list(read_jsonl(stream))
    assert result == [{"pmid": "1", "title": "A"}, {"pmid": "2", "title": "B"}]


def test_malformed_lines_skipped() -> None:
    """Malformed JSON lines are silently skipped."""
    stream = io.StringIO('{"pmid": "1"}\nnot json\n{"pmid": "2"}\n')
    result = list(read_jsonl(stream))
    assert result == [{"pmid": "1"}, {"pmid": "2"}]


def test_empty_lines_skipped() -> None:
    """Empty and whitespace-only lines are skipped."""
    stream = io.StringIO('{"pmid": "1"}\n\n   \n{"pmid": "2"}\n')
    result = list(read_jsonl(stream))
    assert result == [{"pmid": "1"}, {"pmid": "2"}]


def test_non_dict_json_values_skipped() -> None:
    """JSON values that are not dicts (strings, arrays, numbers) are skipped."""
    stream = io.StringIO('"just a string"\n[1, 2, 3]\n42\n{"pmid": "1"}\nnull\ntrue\n')
    result = list(read_jsonl(stream))
    assert result == [{"pmid": "1"}]


def test_empty_stream() -> None:
    """An empty stream yields nothing."""
    stream = io.StringIO("")
    result = list(read_jsonl(stream))
    assert result == []


def test_returns_iterator() -> None:
    """read_jsonl returns a lazy iterator, not a list."""
    stream = io.StringIO('{"a": 1}\n')
    result = read_jsonl(stream)
    # Should be an iterator, not a list
    assert hasattr(result, "__next__")
