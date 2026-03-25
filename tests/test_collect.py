"""Tests for pm collect command."""

from unittest.mock import patch

import pytest

from pm_tools.cli import collect_main


class TestCollectArgs:
    """Test collect argument parsing."""

    def test_multi_word_query_accepted(self) -> None:
        """Multi-word query without quotes should work (currently fails with exit 2)."""
        with (
            patch("pm_tools.cli.search") as mock_search,
            patch("pm_tools.cli.fetch") as mock_fetch,
            patch("pm_tools.cli.parse") as mock_parse,
            patch("pm_tools.cli.collect_main.__module__", create=True),
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["12345"]
            mock_fetch.fetch.return_value = "<xml/>"
            mock_parse.parse_xml.return_value = [{"pmid": "12345", "title": "Test"}]
            mock_parse.LEGACY_FIELDS = {"pmid", "title"}
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
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["12345"]
            mock_fetch.fetch.return_value = "<xml/>"
            mock_parse.parse_xml.return_value = [{"pmid": "12345", "title": "Test"}]
            mock_parse.LEGACY_FIELDS = {"pmid", "title"}
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
            patch("pm_tools.cache.find_pm_dir", return_value=None),
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
            patch("pm_tools.cache.find_pm_dir", return_value=None),
        ):
            mock_search.search.return_value = ["12345"]
            mock_fetch.fetch.return_value = "<xml/>"
            mock_parse.parse_xml.return_value = [{"pmid": "12345", "title": "Test"}]
            mock_parse.LEGACY_FIELDS = {"pmid", "title"}
            result = collect_main(["CRISPR", "-n", "3"])
            assert result == 0
            call_args = mock_search.search.call_args
            assert call_args[0][1] == 3


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
