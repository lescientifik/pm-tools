"""Tests for pm_tools.refs — extract cited PMIDs/DOIs from NXML files.

RED phase: tests written before implementation to drive extract_refs().
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest

from pm_tools.download import (
    download_articles,
    find_sources,
)
from pm_tools.refs import extract_refs
from pm_tools.refs import main as refs_main
from tests.conftest import make_tgz as _make_tgz

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

_NXML_PUBID_OUTSIDE_REFLIST = """\
<article>
  <front>
    <article-meta>
      <article-id pub-id-type="pmid">99999999</article-id>
      <pub-id pub-id-type="pmid">88888888</pub-id>
    </article-meta>
  </front>
  <back>
    <ref-list>
      <ref id="R1">
        <mixed-citation>
          <pub-id pub-id-type="pmid">11111111</pub-id>
        </mixed-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

_NXML_NESTED_REFLIST = """\
<article>
  <back>
    <ref-list>
      <title>Main References</title>
      <ref id="R1">
        <mixed-citation>
          <pub-id pub-id-type="pmid">11111111</pub-id>
        </mixed-citation>
      </ref>
      <ref-list>
        <title>Supplementary References</title>
        <ref id="S1">
          <mixed-citation>
            <pub-id pub-id-type="pmid">22222222</pub-id>
          </mixed-citation>
        </ref>
      </ref-list>
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

    def test_invalid_xml_raises_parse_error(self) -> None:
        """Invalid XML input raises ET.ParseError."""
        import xml.etree.ElementTree as ET

        with pytest.raises(ET.ParseError):
            extract_refs("<not-valid-xml><<<")

    def test_empty_string_returns_empty(self) -> None:
        """Empty/whitespace input still returns empty list (not ParseError)."""
        assert extract_refs("") == []
        assert extract_refs("   ") == []

    def test_whitespace_only_pmid_skipped(self) -> None:
        """Whitespace-only PMID text is skipped, not emitted."""
        result = extract_refs(_NXML_WHITESPACE_PMID)
        assert result == ["33333333"]

    def test_pubid_outside_reflist_ignored(self) -> None:
        """<pub-id> in <front> or <article-meta> is NOT extracted — only <ref-list>."""
        result = extract_refs(_NXML_PUBID_OUTSIDE_REFLIST)
        assert result == ["11111111"]
        assert "88888888" not in result
        assert "99999999" not in result

    def test_nested_reflist(self) -> None:
        """Nested <ref-list> elements — PMIDs from both levels are extracted."""
        result = extract_refs(_NXML_NESTED_REFLIST)
        assert result == ["11111111", "22222222"]

    def test_doctype_xxe_safe(self) -> None:
        """XML with DOCTYPE declaration raises ParseError (ET rejects external entities)."""
        import xml.etree.ElementTree as ET

        malicious = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            "<article><back><ref-list>"
            '<ref><mixed-citation><pub-id pub-id-type="pmid">&xxe;</pub-id>'
            "</mixed-citation></ref>"
            "</ref-list></back></article>"
        )
        # ET.fromstring rejects DTDs with external entities → ParseError
        with pytest.raises(ET.ParseError):
            extract_refs(malicious)

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

    def test_file_arg_prints_pmids(self, capsys: pytest.CaptureFixture[str]) -> None:
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
            "<article><back><ref-list>"
            "<ref><mixed-citation>"
            '<pub-id pub-id-type="pmid">22222222</pub-id>'
            "</mixed-citation></ref>"
            "<ref><mixed-citation>"
            '<pub-id pub-id-type="pmid">33333333</pub-id>'
            "</mixed-citation></ref>"
            "</ref-list></back></article>"
        )
        exit_code = refs_main([str(f1), str(f2)])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        assert lines == ["11111111", "22222222", "33333333"]

    def test_doi_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """pm refs --doi file.nxml prints DOIs instead."""
        exit_code = refs_main(["--doi", str(SAMPLE_NXML)])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        assert lines == ["10.1038/example", "10.1000/other"]

    def test_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """pm refs --help prints help text and exits with 0."""
        result = refs_main(["--help"])
        assert result == 0
        captured = capsys.readouterr()
        assert "pm refs" in captured.out
        assert "--doi" in captured.out

    def test_nonexistent_file_error(self, capsys: pytest.CaptureFixture[str]) -> None:
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

    def test_multifile_continues_on_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Multi-file: bad file doesn't discard already-collected refs; exit 1."""
        good = tmp_path / "good.nxml"
        good.write_text(SAMPLE_NXML.read_text())
        bad = tmp_path / "missing.nxml"  # does not exist

        exit_code = refs_main([str(good), str(bad)])
        assert exit_code == 1
        captured = capsys.readouterr()
        # Refs from the good file should still be printed
        lines = captured.out.strip().splitlines()
        assert "11111111" in lines
        assert "22222222" in lines
        # Error about the bad file on stderr
        assert "Error" in captured.err

    def test_output_lines_are_pmids(self, capsys: pytest.CaptureFixture[str]) -> None:
        """pm refs output lines are all-digit PMIDs (pipeable to pm fetch)."""
        exit_code = refs_main([str(SAMPLE_NXML)])
        assert exit_code == 0
        captured = capsys.readouterr()
        for line in captured.out.strip().splitlines():
            assert line.isdigit(), f"Expected all-digit PMID, got: {line!r}"


# ---------------------------------------------------------------------------
# Integration tests — compose download + refs
# ---------------------------------------------------------------------------

_FAKE_PDF = b"%PDF-1.4 test content"


def _make_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


_PMC_OA_TGZ_ONLY_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<OA><records>"
    '<record id="PMC9273392" citation="X" license="CC BY">'
    '<link format="tgz"'
    ' href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/46/ea/PMC9273392.tar.gz" />'
    "</record>"
    "</records></OA>"
)

_PMC_OA_PDF_ONLY_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<OA><records>"
    '<record id="PMC12345" citation="X" license="CC BY">'
    '<link format="pdf"'
    ' href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/ab/cd/PMC12345.pdf" />'
    "</record>"
    "</records></OA>"
)


class TestIntegrationDownloadRefs:
    """E2E tests composing pm download + pm refs."""

    def test_e2e_tgz_nxml_then_refs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """tgz with NXML+PDF → download (default) → .nxml → pm refs → PMIDs."""
        output_dir = tmp_path / "articles"
        nxml_content = SAMPLE_NXML.read_text()
        tgz = _make_tgz(
            {
                "PMC9273392/article.nxml": nxml_content.encode(),
                "PMC9273392/article.pdf": _FAKE_PDF,
            }
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                return httpx.Response(status_code=200, text=_PMC_OA_TGZ_ONLY_XML)
            return httpx.Response(status_code=200, content=tgz)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [{"pmid": "1", "pmcid": "PMC9273392"}]
        sources = find_sources(articles)
        result = download_articles(sources, output_dir)

        assert result["downloaded"] == 1
        nxml_path = output_dir / "1.nxml"
        assert nxml_path.exists()

        # Now run pm refs on the downloaded NXML
        exit_code = refs_main([str(nxml_path)])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        assert "11111111" in lines
        assert "22222222" in lines

    def test_e2e_tgz_pdf_only_fallback(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """tgz with only PDF (no NXML) → download → falls back to .pdf."""
        output_dir = tmp_path / "articles"
        tgz = _make_tgz({"PMC9273392/article.pdf": _FAKE_PDF})

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                return httpx.Response(status_code=200, text=_PMC_OA_TGZ_ONLY_XML)
            return httpx.Response(status_code=200, content=tgz)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [{"pmid": "1", "pmcid": "PMC9273392"}]
        sources = find_sources(articles)
        result = download_articles(sources, output_dir)

        assert result["downloaded"] == 1
        assert (output_dir / "1.pdf").exists()
        assert not (output_dir / "1.nxml").exists()

    def test_e2e_pdf_flag_saves_pdf(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """pm download --pdf + tgz with NXML → saves .pdf, not .nxml."""
        output_dir = tmp_path / "articles"
        nxml_content = SAMPLE_NXML.read_text()
        tgz = _make_tgz(
            {
                "PMC9273392/article.nxml": nxml_content.encode(),
                "PMC9273392/article.pdf": _FAKE_PDF,
            }
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                return httpx.Response(status_code=200, text=_PMC_OA_TGZ_ONLY_XML)
            return httpx.Response(status_code=200, content=tgz)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [{"pmid": "1", "pmcid": "PMC9273392"}]
        sources = find_sources(articles)
        result = download_articles(sources, output_dir, prefer_pdf=True)

        assert result["downloaded"] == 1
        assert (output_dir / "1.pdf").exists()
        assert not (output_dir / "1.nxml").exists()

    def test_e2e_mixed_sources(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mixed sources (tgz + direct PDF) → correct file types."""
        output_dir = tmp_path / "articles"
        nxml_content = SAMPLE_NXML.read_text()
        tgz = _make_tgz(
            {
                "PMC9273392/article.nxml": nxml_content.encode(),
                "PMC9273392/article.pdf": _FAKE_PDF,
            }
        )
        direct_pdf = b"%PDF-1.4 direct download"

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                if "PMC12345" in url:
                    return httpx.Response(status_code=200, text=_PMC_OA_PDF_ONLY_XML)
                if "PMC9273392" in url:
                    return httpx.Response(status_code=200, text=_PMC_OA_TGZ_ONLY_XML)
            if "oa_pdf" in url:
                return httpx.Response(status_code=200, content=direct_pdf)
            if "oa_package" in url:
                return httpx.Response(status_code=200, content=tgz)
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [
            {"pmid": "1", "pmcid": "PMC12345"},
            {"pmid": "2", "pmcid": "PMC9273392"},
        ]
        sources = find_sources(articles)
        result = download_articles(sources, output_dir)

        assert result["downloaded"] == 2
        # Article 1: direct PDF → .pdf
        assert (output_dir / "1.pdf").exists()
        # Article 2: tgz → NXML extracted
        assert (output_dir / "2.nxml").exists()

    def test_refs_on_pdf_returns_empty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pm refs on a PDF file → empty output, warning on stderr, exit 0."""
        pdf_file = tmp_path / "article.pdf"
        pdf_file.write_bytes(_FAKE_PDF)

        exit_code = refs_main([str(pdf_file)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == ""
        assert "warning" in captured.err.lower()


# ---------------------------------------------------------------------------
# Phase 5 — warnings on invalid XML / 0 results
# ---------------------------------------------------------------------------


class TestRefsWarnings:
    """Test stderr warnings for edge cases."""

    def test_invalid_xml_warns_on_stderr(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Piping invalid XML → stderr warning, exit 0."""
        bad_file = tmp_path / "bad.nxml"
        bad_file.write_text("<not-valid-xml><<<")
        exit_code = refs_main([str(bad_file)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "warning: could not parse XML" in captured.err

    def test_valid_xml_no_refs_warns(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Valid XML with no ref-list → stderr warning, exit 0."""
        nxml_file = tmp_path / "noref.nxml"
        nxml_file.write_text(_NXML_NO_REFLIST)
        exit_code = refs_main([str(nxml_file)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "warning: no references found" in captured.err

    def test_valid_nxml_with_refs_no_warning(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Valid NXML with refs → no warning on stderr."""
        exit_code = refs_main([str(SAMPLE_NXML)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "warning" not in captured.err.lower()

    def test_multifile_invalid_plus_valid(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Multi-file: bad XML warns, good file refs still printed, exit 0."""
        bad = tmp_path / "bad.nxml"
        bad.write_text("<broken><<<xml")
        good = tmp_path / "good.nxml"
        good.write_text(SAMPLE_NXML.read_text())
        exit_code = refs_main([str(bad), str(good)])
        assert exit_code == 0
        captured = capsys.readouterr()
        # Warning for bad file
        assert "warning: could not parse XML" in captured.err
        # Refs from good file still printed
        lines = captured.out.strip().splitlines()
        assert "11111111" in lines
        assert "22222222" in lines

    def test_multifile_invalid_plus_no_refs_warns_both(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Parse error + valid-but-no-refs → both warnings emitted."""
        bad = tmp_path / "bad.nxml"
        bad.write_text("<broken><<<xml")
        no_refs = tmp_path / "noref.nxml"
        no_refs.write_text(_NXML_NO_REFLIST)
        exit_code = refs_main([str(bad), str(no_refs)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "warning: could not parse XML" in captured.err
        assert "warning: no references found" in captured.err
