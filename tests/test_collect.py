"""Tests for pm collect command."""

from unittest.mock import patch

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

    def test_empty_query_returns_1(self, capsys: object) -> None:
        """No query args should print error to stderr and return 1."""
        result = collect_main([])
        assert result == 1
        captured = capsys.readouterr()  # type: ignore[union-attr]
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
