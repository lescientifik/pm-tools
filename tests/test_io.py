"""Tests for pm_tools.io — shared JSONL utilities and input validation."""

from __future__ import annotations

import io

import pytest

from pm_tools.io import read_jsonl, validate_filename_safe, validate_pmid


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
# validate_pmid — strict numeric-only (for E-utilities)
# ---------------------------------------------------------------------------


class TestValidatePmid:
    """validate_pmid accepts only numeric strings (E-utilities PMIDs)."""

    def test_valid_numeric_pmid(self) -> None:
        """A plain numeric PMID passes validation and is returned."""
        assert validate_pmid("12345678") == "12345678"

    def test_path_traversal_rejected(self) -> None:
        """Path traversal attempts raise ValueError."""
        with pytest.raises(ValueError, match="Invalid PMID"):
            validate_pmid("../../etc/passwd")

    def test_pmc_id_rejected(self) -> None:
        """PMC IDs are rejected — E-utilities require numeric-only PMIDs."""
        with pytest.raises(ValueError, match="Invalid PMID"):
            validate_pmid("PMC1234567")

    def test_empty_string_rejected(self) -> None:
        """An empty string is not a valid PMID."""
        with pytest.raises(ValueError, match="Invalid PMID"):
            validate_pmid("")

    def test_whitespace_only_rejected(self) -> None:
        """Whitespace-only strings are not valid PMIDs."""
        with pytest.raises(ValueError, match="Invalid PMID"):
            validate_pmid("  ")

    def test_null_byte_rejected(self) -> None:
        """Null bytes embedded in a PMID are rejected."""
        with pytest.raises(ValueError, match="Invalid PMID"):
            validate_pmid("123\x00456")

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

    def test_path_traversal_rejected(self) -> None:
        """Path traversal attempts raise ValueError."""
        with pytest.raises(ValueError, match="not filename-safe"):
            validate_filename_safe("../../etc/passwd")

    def test_null_byte_rejected(self) -> None:
        """Null bytes raise ValueError."""
        with pytest.raises(ValueError, match="not filename-safe"):
            validate_filename_safe("foo\x00bar")

    def test_slash_rejected(self) -> None:
        """Forward slashes are not allowed in filenames."""
        with pytest.raises(ValueError, match="not filename-safe"):
            validate_filename_safe("foo/bar")

    def test_backslash_rejected(self) -> None:
        """Backslashes are not allowed in filenames."""
        with pytest.raises(ValueError, match="not filename-safe"):
            validate_filename_safe("foo\\bar")

    def test_empty_string_rejected(self) -> None:
        """An empty string is not a valid filename."""
        with pytest.raises(ValueError, match="not filename-safe"):
            validate_filename_safe("")
