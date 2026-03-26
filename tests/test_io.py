"""Tests for pm_tools.io — shared JSONL utilities, input validation, and argument parsing."""

from __future__ import annotations

import argparse
import io
import logging

import pytest

from pm_tools.io import (
    detect_input_format,
    read_jsonl,
    read_pmids_from_lines,
    safe_parse,
    validate_filename_safe,
    validate_pmid,
)


def test_valid_jsonl_yields_dicts() -> None:
    """Valid JSONL lines with dict objects are yielded."""
    stream = io.StringIO('{"pmid": "1", "title": "A"}\n{"pmid": "2", "title": "B"}\n')
    result = list(read_jsonl(stream))
    assert result == [{"pmid": "1", "title": "A"}, {"pmid": "2", "title": "B"}]


def test_malformed_lines_skipped() -> None:
    """Malformed JSON lines are skipped."""
    stream = io.StringIO('{"pmid": "1"}\nnot json\n{"pmid": "2"}\n')
    result = list(read_jsonl(stream))
    assert result == [{"pmid": "1"}, {"pmid": "2"}]


def test_malformed_line_emits_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Malformed JSON lines emit a logging.WARNING with line number."""
    stream = io.StringIO('{"pmid": "1"}\nnot json\n{"pmid": "2"}\n')
    with caplog.at_level(logging.WARNING, logger="pm_tools.io"):
        list(read_jsonl(stream))
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "line 2" in caplog.records[0].message


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



# ---------------------------------------------------------------------------
# validate_pmid — strict numeric-only (for E-utilities)
# ---------------------------------------------------------------------------


class TestValidatePmid:
    """validate_pmid accepts only numeric strings (E-utilities PMIDs)."""

    def test_valid_numeric_pmid(self) -> None:
        """A plain numeric PMID passes validation and is returned."""
        assert validate_pmid("12345678") == "12345678"

    @pytest.mark.parametrize(
        "bad_pmid",
        [
            "../../etc/passwd",  # path traversal
            "PMC1234567",        # PMC ID (not numeric)
            "",                  # empty string
            "  ",                # whitespace only
            "123\x00456",        # null byte
        ],
    )
    def test_invalid_pmid_rejected(self, bad_pmid: str) -> None:
        """Non-numeric and malicious strings raise ValueError."""
        with pytest.raises(ValueError, match="Invalid PMID"):
            validate_pmid(bad_pmid)

    def test_leading_zeros_accepted(self) -> None:
        """PMIDs with leading zeros are valid."""
        assert validate_pmid("00123") == "00123"


# ---------------------------------------------------------------------------
# validate_filename_safe — alphanumeric + limited chars (for filesystem ops)
# ---------------------------------------------------------------------------


class TestValidateFilenameSafe:
    """validate_filename_safe accepts PMIDs and PMC IDs but rejects path tricks."""

    def test_numeric_pmid_accepted(self) -> None:
        """A plain numeric PMID passes validation."""
        assert validate_filename_safe("12345678") == "12345678"

    def test_pmc_id_accepted(self) -> None:
        """A PMC ID like PMC1234567 is accepted."""
        assert validate_filename_safe("PMC1234567") == "PMC1234567"

    @pytest.mark.parametrize(
        "bad_name",
        [
            "../../etc/passwd",  # path traversal
            "foo\x00bar",        # null byte
            "foo/bar",           # forward slash
            "foo\\bar",          # backslash
            "",                  # empty string
        ],
    )
    def test_invalid_filename_rejected(self, bad_name: str) -> None:
        """Unsafe filenames raise ValueError."""
        with pytest.raises(ValueError, match="not filename-safe"):
            validate_filename_safe(bad_name)


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


# ---------------------------------------------------------------------------
# detect_input_format — detect JSONL vs plain PMIDs from first line
# ---------------------------------------------------------------------------


class TestDetectInputFormat:
    """detect_input_format inspects the first non-empty line."""

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("12345", "plain"),              # numeric PMID
            ('{"pmid": "12345"}', "jsonl"),  # JSON dict
            ('{"pmid": "123"', "plain"),     # truncated JSON
        ],
    )
    def test_format_detection(self, line: str, expected: str) -> None:
        """detect_input_format returns correct format for each line type."""
        assert detect_input_format(line) == expected

    def test_whitespace_stripped_before_detection(self) -> None:
        """Leading/trailing whitespace is stripped before detection."""
        assert detect_input_format('  {"pmid": "12345"}  ') == "jsonl"


# ---------------------------------------------------------------------------
# read_pmids_from_lines — extract PMIDs from plain or JSONL input
# ---------------------------------------------------------------------------


class TestReadPmidsFromLines:
    """read_pmids_from_lines auto-detects format and extracts PMIDs."""

    def test_plain_pmids(self) -> None:
        """Plain numeric lines are returned as-is."""
        assert read_pmids_from_lines(["12345", "67890"]) == ["12345", "67890"]

    def test_jsonl_with_pmid_key(self) -> None:
        """JSONL lines with 'pmid' key extract the pmid value."""
        lines = ['{"pmid": "12345", "title": "X"}']
        assert read_pmids_from_lines(lines) == ["12345"]

    def test_blank_lines_skipped(self) -> None:
        """Empty and whitespace-only lines are skipped."""
        assert read_pmids_from_lines(["", "  ", "12345"]) == ["12345"]

    def test_jsonl_whitespace_stripped(self) -> None:
        """Whitespace around JSONL lines is stripped before parsing."""
        assert read_pmids_from_lines(['  {"pmid": "12345"}  ']) == ["12345"]

    def test_jsonl_without_pmid_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """JSONL lines missing 'pmid' key emit a warning and are skipped."""
        with caplog.at_level(logging.WARNING, logger="pm_tools.io"):
            result = read_pmids_from_lines(['{"no_pmid": true}'])
        assert result == []
        assert any("pmid" in r.message.lower() for r in caplog.records)

    def test_jsonl_mode_skips_non_json_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """In JSONL mode, non-JSON lines are skipped with a warning."""
        with caplog.at_level(logging.WARNING, logger="pm_tools.io"):
            result = read_pmids_from_lines(['{"pmid": "111"}', "not json"])
        assert result == ["111"]
        assert any(
            "malformed" in r.message.lower() or "json" in r.message.lower()
            for r in caplog.records
        )

    def test_plain_mode_returns_raw_lines(self) -> None:
        """In plain mode, later JSON-looking lines are returned as raw strings."""
        result = read_pmids_from_lines(["12345", '{"pmid": "67890"}'])
        assert result == ["12345", '{"pmid": "67890"}']

    def test_empty_input(self) -> None:
        """Empty iterable returns empty list."""
        assert read_pmids_from_lines([]) == []

    def test_truncated_json_triggers_plain_mode(self) -> None:
        """Truncated JSON on first line commits to plain mode."""
        result = read_pmids_from_lines(['{"pmid": "123"', '{"pmid": "456"}'])
        assert result == ['{"pmid": "123"', '{"pmid": "456"}']
