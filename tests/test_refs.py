"""Tests for pm_tools.refs — extract cited PMIDs/DOIs from NXML files.

RED phase: tests written before implementation to drive extract_refs().
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pm_tools.refs import extract_refs
from pm_tools.refs import main as refs_main

FIXTURES = Path(__file__).parent.parent / "fixtures"
GOLDEN = FIXTURES / "golden"
SAMPLE_NXML = FIXTURES / "sample.nxml"


# ---------------------------------------------------------------------------
# Helpers — inline NXML fragments
# ---------------------------------------------------------------------------

_NXML_BOTH_IDS = """\
<article>
  <back>
    <ref-list>
      <ref id="R1">
        <mixed-citation>
          <pub-id pub-id-type="pmid">11111111</pub-id>
          <pub-id pub-id-type="doi">10.1038/example</pub-id>
        </mixed-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

_NXML_NO_REFLIST = """\
<article>
  <front><article-meta><article-id pub-id-type="pmid">99999</article-id></article-meta></front>
  <body><p>No references here.</p></body>
</article>
"""

_NXML_NO_PMID_REFS = """\
<article>
  <back>
    <ref-list>
      <ref id="R1">
        <mixed-citation>
          <pub-id pub-id-type="doi">10.1000/nopmid</pub-id>
        </mixed-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

_NXML_DUPLICATES = """\
<article>
  <back>
    <ref-list>
      <ref id="R1">
        <mixed-citation>
          <pub-id pub-id-type="pmid">11111111</pub-id>
        </mixed-citation>
      </ref>
      <ref id="R2">
        <mixed-citation>
          <pub-id pub-id-type="pmid">22222222</pub-id>
        </mixed-citation>
      </ref>
      <ref id="R3">
        <mixed-citation>
          <pub-id pub-id-type="pmid">11111111</pub-id>
        </mixed-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

_NXML_WHITESPACE_PMID = """\
<article>
  <back>
    <ref-list>
      <ref id="R1">
        <mixed-citation>
          <pub-id pub-id-type="pmid">  </pub-id>
        </mixed-citation>
      </ref>
      <ref id="R2">
        <mixed-citation>
          <pub-id pub-id-type="pmid">33333333</pub-id>
        </mixed-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""


# ---------------------------------------------------------------------------
# TestExtractRefs — core function
# ---------------------------------------------------------------------------


class TestExtractRefs:
    """Tests for extract_refs() core function."""

    def test_nxml_with_pmids(self) -> None:
        """NXML with ref-list containing PMIDs returns list of PMID strings."""
        content = SAMPLE_NXML.read_text()
        result = extract_refs(content)
        assert result == ["11111111", "22222222"]

    def test_mixed_and_element_citation(self) -> None:
        """Finds PMIDs in both mixed-citation and element-citation."""
        content = SAMPLE_NXML.read_text()
        result = extract_refs(content)
        # B1 is mixed-citation, B2 is element-citation — both found
        assert "11111111" in result
        assert "22222222" in result

    def test_default_returns_pmids_not_dois(self) -> None:
        """Default id_type returns only PMIDs, not DOIs."""
        result = extract_refs(_NXML_BOTH_IDS)
        assert result == ["11111111"]

    def test_doi_mode(self) -> None:
        """id_type='doi' returns DOIs instead of PMIDs."""
        content = SAMPLE_NXML.read_text()
        result = extract_refs(content, id_type="doi")
        assert result == ["10.1038/example", "10.1000/other"]

    def test_no_reflist(self) -> None:
        """NXML with no ref-list returns empty list."""
        result = extract_refs(_NXML_NO_REFLIST)
        assert result == []

    def test_no_pmid_refs(self) -> None:
        """NXML with refs but no pub-id type=pmid returns empty list."""
        result = extract_refs(_NXML_NO_PMID_REFS)
        assert result == []

    def test_duplicates_deduplicated(self) -> None:
        """Duplicate PMIDs across refs are deduplicated, order preserved."""
        result = extract_refs(_NXML_DUPLICATES)
        assert result == ["11111111", "22222222"]

    def test_empty_string(self) -> None:
        """Empty string input returns empty list."""
        result = extract_refs("")
        assert result == []

    def test_invalid_xml(self) -> None:
        """Invalid XML input returns empty list (no crash)."""
        result = extract_refs("<not-valid-xml><<<")
        assert result == []

    def test_whitespace_only_pmid_skipped(self) -> None:
        """Whitespace-only PMID text is skipped, not emitted."""
        result = extract_refs(_NXML_WHITESPACE_PMID)
        assert result == ["33333333"]

    def test_golden_pmids(self) -> None:
        """Golden file sample-refs-pmids.txt matches extract_refs(sample.nxml)."""
        content = SAMPLE_NXML.read_text()
        expected = GOLDEN.joinpath("sample-refs-pmids.txt").read_text().strip().splitlines()
        result = extract_refs(content)
        assert result == expected

    def test_golden_dois(self) -> None:
        """Golden file sample-refs-dois.txt matches extract_refs(sample.nxml, 'doi')."""
        content = SAMPLE_NXML.read_text()
        expected = GOLDEN.joinpath("sample-refs-dois.txt").read_text().strip().splitlines()
        result = extract_refs(content, id_type="doi")
        assert result == expected


# ---------------------------------------------------------------------------
# TestRefsCli — pm refs CLI
# ---------------------------------------------------------------------------


class TestRefsCli:
    """Tests for pm refs CLI entry point."""

    def test_file_arg_prints_pmids(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pm refs file.nxml reads file and prints PMIDs to stdout."""
        exit_code = refs_main([str(SAMPLE_NXML)])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        assert lines == ["11111111", "22222222"]

    def test_stdin_reads_nxml(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pm refs with stdin reads NXML from stdin."""
        content = SAMPLE_NXML.read_text()
        monkeypatch.setattr("sys.stdin", io.StringIO(content))
        # Simulate non-tty stdin
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        exit_code = refs_main([])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        assert lines == ["11111111", "22222222"]

    def test_multiple_files_deduplicated(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pm refs *.nxml processes multiple files, output is union (deduplicated)."""
        # File 1: PMIDs 11111111, 22222222
        f1 = tmp_path / "a.nxml"
        f1.write_text(SAMPLE_NXML.read_text())
        # File 2: PMID 22222222 (duplicate) + 33333333
        f2 = tmp_path / "b.nxml"
        f2.write_text(
            '<article><back><ref-list>'
            '<ref><mixed-citation>'
            '<pub-id pub-id-type="pmid">22222222</pub-id>'
            '</mixed-citation></ref>'
            '<ref><mixed-citation>'
            '<pub-id pub-id-type="pmid">33333333</pub-id>'
            '</mixed-citation></ref>'
            '</ref-list></back></article>'
        )
        exit_code = refs_main([str(f1), str(f2)])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        assert lines == ["11111111", "22222222", "33333333"]

    def test_doi_flag(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pm refs --doi file.nxml prints DOIs instead."""
        exit_code = refs_main(["--doi", str(SAMPLE_NXML)])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        assert lines == ["10.1038/example", "10.1000/other"]

    def test_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """pm refs --help prints help text."""
        exit_code = refs_main(["--help"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "pm refs" in captured.out
        assert "--doi" in captured.out

    def test_nonexistent_file_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pm refs nonexistent.nxml prints error to stderr, exit 1."""
        exit_code = refs_main(["/nonexistent/path/file.nxml"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_no_input_no_tty_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pm refs with no args and stdin is tty shows error."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        exit_code = refs_main([])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_output_lines_are_pmids(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pm refs output lines are all-digit PMIDs (pipeable to pm fetch)."""
        exit_code = refs_main([str(SAMPLE_NXML)])
        assert exit_code == 0
        captured = capsys.readouterr()
        for line in captured.out.strip().splitlines():
            assert line.isdigit(), f"Expected all-digit PMID, got: {line!r}"
