"""Tests for pm collect command."""

import json
from unittest.mock import patch

import pytest

from pm_tools.cli import collect_main

# Minimal two-article XML for end-to-end CLI tests.
_COLLECT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>111</PMID>
    <Article>
      <ArticleTitle>First</ArticleTitle>
      <Journal>
        <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue>
        <Title>J1</Title>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
<PubmedArticle>
  <MedlineCitation>
    <PMID>222</PMID>
    <Article>
      <ArticleTitle>Second</ArticleTitle>
      <Journal>
        <JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue>
        <Title>J2</Title>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""


class TestCollectMaxValidation:
    """Test --max rejects invalid values and -n alias works."""

    def test_max_zero_returns_exit_2(self) -> None:
        """--max 0 should be rejected by argparse (exit 2)."""
        result = collect_main(["CRISPR", "--max", "0"])
        assert result == 2

    def test_max_negative_returns_exit_2(self) -> None:
        """--max -5 should be rejected by argparse (exit 2)."""
        result = collect_main(["CRISPR", "--max", "-5"])
        assert result == 2



# =============================================================================
# collect_main streaming wiring (Phase 1.2)
# =============================================================================


class TestCollectStreamingWiring:
    """collect_main must use parse_xml_stream, not parse_xml."""

    def test_collect_jsonl_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """collect_main produces correct JSONL output with mocked search+fetch."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["111", "222"]
            mock_fetch.fetch.return_value = _COLLECT_XML
            rc = collect_main(["test", "query"])

        assert rc == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["pmid"] == "111"
        assert first["title"] == "First"
        assert second["pmid"] == "222"
        assert second["title"] == "Second"



# =============================================================================
# --count flag (Phase 3b)
# =============================================================================


# Minimal single-article XML for CSL flag tests.
_CSL_XML = """\
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99999</PMID>
    <Article>
      <Journal>
        <ISSN IssnType="Print">0300-9629</ISSN>
        <JournalIssue CitedMedium="Print">
          <Volume>48</Volume>
          <Issue>2</Issue>
          <PubDate><Year>2024</Year></PubDate>
        </JournalIssue>
        <Title>Test Journal</Title>
        <ISOAbbreviation>Test J</ISOAbbreviation>
      </Journal>
      <ArticleTitle>Test Title</ArticleTitle>
      <Pagination><MedlinePgn>100-105</MedlinePgn></Pagination>
      <AuthorList>
        <Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
      </AuthorList>
      <ELocationID EIdType="doi" ValidYN="Y">10.1234/test</ELocationID>
    </Article>
    <MedlineJournalInfo>
      <Country>England</Country>
    </MedlineJournalInfo>
  </MedlineCitation>
  <PubmedData>
    <PublicationStatus>ppublish</PublicationStatus>
    <ArticleIdList>
      <ArticleId IdType="pmc">PMC1234567</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""


class TestCollectCslFlag:
    """pm collect --csl produces CSL-JSON output."""

    def test_collect_with_csl_produces_csl(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """collect_main(["query", "--csl"]) produces CSL-JSON."""
        with (
            patch("pm_tools.search.search", return_value=["99999"]),
            patch("pm_tools.fetch.fetch", return_value=_CSL_XML),
            patch("pm_tools.cli.find_pm_dir", return_value=None),
        ):
            result = collect_main(["test query", "--csl"])

        assert result == 0
        output = capsys.readouterr().out.strip()
        record = json.loads(output)
        assert record["type"] == "article-journal"
        assert "container-title" in record


# =============================================================================
# --count flag (Phase 3b)
# =============================================================================


class TestCollectCountFlag:
    """collect_main --count prints a single integer instead of JSONL articles."""

    def test_count_outputs_integer(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--count outputs a single line with an integer on stdout, nothing else."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["111", "222"]
            mock_fetch.fetch.return_value = _COLLECT_XML
            rc = collect_main(["CRISPR", "--max", "5", "--count"])

        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert out == "2"

    def test_count_and_csl_mutually_exclusive(self) -> None:
        """--count and --csl together should cause argparse error (exit 2)."""
        rc = collect_main(["CRISPR", "--max", "5", "--count", "--csl"])
        assert rc == 2

    def test_count_with_verbose(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--count with -v: integer on stdout, progress on stderr."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["111", "222"]
            mock_fetch.fetch.return_value = _COLLECT_XML
            rc = collect_main(["CRISPR", "--max", "5", "--count", "-v"])

        assert rc == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "2"
        assert "Searching PubMed" in captured.err

    def test_count_zero_results(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--count with zero search results outputs 0."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = []
            rc = collect_main(["nonexistent-query", "--max", "5", "--count"])

        assert rc == 0
        assert capsys.readouterr().out.strip() == "0"
