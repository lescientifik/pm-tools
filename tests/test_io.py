"""Tests for pm_tools.io — shared JSONL utilities and argument parsing."""

from __future__ import annotations

import argparse
import io

import pytest

from pm_tools.io import read_jsonl, safe_parse


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


# ---------------------------------------------------------------------------
# safe_parse — wraps argparse to avoid SystemExit leaking into callers
# ---------------------------------------------------------------------------


class TestSafeParse:
    """safe_parse catches SystemExit from argparse and returns a tuple."""

    @pytest.fixture()
    def parser(self) -> argparse.ArgumentParser:
        """A minimal parser with one required positional arg."""
        p = argparse.ArgumentParser(prog="test")
        p.add_argument("name")
        return p

    def test_valid_args_returns_namespace(
        self, parser: argparse.ArgumentParser
    ) -> None:
        """Valid args return (Namespace, None)."""
        ns, code = safe_parse(parser, ["hello"])
        assert ns is not None
        assert code is None
        assert ns.name == "hello"

    def test_help_returns_zero(self, parser: argparse.ArgumentParser) -> None:
        """--help triggers SystemExit(0); safe_parse returns (None, 0)."""
        ns, code = safe_parse(parser, ["--help"])
        assert ns is None
        assert code == 0

    def test_invalid_args_returns_two(
        self, parser: argparse.ArgumentParser
    ) -> None:
        """Missing required arg triggers SystemExit(2); safe_parse returns (None, 2)."""
        ns, code = safe_parse(parser, [])
        assert ns is None
        assert code == 2

    def test_exit_code_preserved_for_bad_type(self) -> None:
        """Invalid type for typed arg preserves argparse exit code (2)."""
        p = argparse.ArgumentParser(prog="test")
        p.add_argument("--count", type=int)
        ns, code = safe_parse(p, ["--count", "abc"])
        assert ns is None
        assert code == 2
