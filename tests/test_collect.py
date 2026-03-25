"""Tests for pm collect command."""

import json
from unittest.mock import patch

import pytest

from pm_tools.cli import collect_main
from pm_tools.parse import format_article

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


class TestCollectArgs:
    """Test collect argument parsing."""

    def test_multi_word_query_accepted(self) -> None:
        """Multi-word query without quotes should work (currently fails with exit 2)."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch("pm_tools.cli.parse") as mock_parse,
            patch("pm_tools.cli.collect_main.__module__", create=True),
            patch("pm_tools.cli.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["12345"]
            mock_fetch.fetch.return_value = "<xml/>"
            mock_parse.parse_xml.return_value = [{"pmid": "12345", "title": "Test"}]
            mock_parse.LEGACY_FIELDS = {"pmid", "title"}
            mock_parse.format_article = format_article
            result = collect_main(["CRISPR", "cancer", "--max", "1"])
            assert result == 0
            call_args = mock_search.search.call_args
            assert call_args[0][0] == "CRISPR cancer"

    def test_single_word_query_still_works(self) -> None:
        """Single word query should still work."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch("pm_tools.cli.parse") as mock_parse,
            patch("pm_tools.cli.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["12345"]
            mock_fetch.fetch.return_value = "<xml/>"
            mock_parse.parse_xml.return_value = [{"pmid": "12345", "title": "Test"}]
            mock_parse.LEGACY_FIELDS = {"pmid", "title"}
            mock_parse.format_article = format_article
            result = collect_main(["CRISPR", "--max", "1"])
            assert result == 0
            call_args = mock_search.search.call_args
            assert call_args[0][0] == "CRISPR"

    def test_empty_query_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """No query args should print error to stderr and return 1."""
        result = collect_main([])
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_quoted_query_still_works(self) -> None:
        """A quoted multi-word query (single argv element) should still work."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch"),
            patch("pm_tools.cli.parse"),
            patch("pm_tools.cli.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = []
            result = collect_main(["CRISPR cancer", "--max", "1"])
            assert result == 0
            call_args = mock_search.search.call_args
            assert call_args[0][0] == "CRISPR cancer"


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

    def test_n_alias_works(self) -> None:
        """-n 3 should be equivalent to --max 3."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch("pm_tools.cli.parse") as mock_parse,
            patch("pm_tools.cli.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["12345"]
            mock_fetch.fetch.return_value = "<xml/>"
            mock_parse.parse_xml.return_value = [{"pmid": "12345", "title": "Test"}]
            mock_parse.LEGACY_FIELDS = {"pmid", "title"}
            mock_parse.format_article = format_article
            result = collect_main(["CRISPR", "-n", "3"])
            assert result == 0
            call_args = mock_search.search.call_args
            assert call_args[0][1] == 3


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
        assert second["pmid"] == "222"

    def test_collect_uses_stream_not_parse_xml(self) -> None:
        """collect_main must call parse.parse_xml_stream, NOT parse.parse_xml."""
        from pm_tools import parse as parse_mod

        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch.object(parse_mod, "parse_xml_stream") as mock_stream,
            patch.object(parse_mod, "parse_xml") as mock_legacy,
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["111"]
            mock_fetch.fetch.return_value = _COLLECT_XML
            mock_stream.return_value = iter([{"pmid": "111", "title": "T1"}])
            rc = collect_main(["test", "query"])

        assert rc == 0
        mock_stream.assert_called_once()
        mock_legacy.assert_not_called()


# =============================================================================
# --refresh flag wiring (Phase 3.1)
# =============================================================================


class TestCollectRefreshFlag:
    """collect_main must accept --refresh and pass refresh=True to search() and fetch()."""

    def test_refresh_passed_to_search_and_fetch(self) -> None:
        """--refresh should forward refresh=True to both search() and fetch()."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch("pm_tools.cli.parse") as mock_parse,
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["111"]
            mock_fetch.fetch.return_value = "<PubmedArticleSet></PubmedArticleSet>"
            mock_parse.parse_xml.return_value = []
            mock_parse.LEGACY_FIELDS = {"pmid", "title"}
            rc = collect_main(["--refresh", "test", "query"])

        assert rc == 0
        # search() must receive refresh=True
        search_kwargs = mock_search.search.call_args
        assert search_kwargs.kwargs.get("refresh") is True
        # fetch() must receive refresh=True
        fetch_kwargs = mock_fetch.fetch.call_args
        assert fetch_kwargs.kwargs.get("refresh") is True

    def test_no_refresh_defaults_false(self) -> None:
        """Without --refresh, refresh should not be True in search()/fetch() calls."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch("pm_tools.cli.parse") as mock_parse,
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["111"]
            mock_fetch.fetch.return_value = "<PubmedArticleSet></PubmedArticleSet>"
            mock_parse.parse_xml.return_value = []
            mock_parse.LEGACY_FIELDS = {"pmid", "title"}
            rc = collect_main(["test", "query"])

        assert rc == 0
        search_kwargs = mock_search.search.call_args
        assert not search_kwargs.kwargs.get("refresh")
        fetch_kwargs = mock_fetch.fetch.call_args
        assert not fetch_kwargs.kwargs.get("refresh")
