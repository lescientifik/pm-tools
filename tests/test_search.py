"""Tests for pm_tools.search — PubMed search returning PMIDs.

Tests the search function at the Python module level, mocking HTTP responses
using httpx.MockTransport for realistic request/response fidelity.

The search module is at pm_tools.search with:
  - search(query: str, max_results: int = 10000) -> list[str]
"""

import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from pm_tools.search import search


def _make_search_client(
    xml_text: str,
    *,
    requests: list[httpx.Request] | None = None,
) -> httpx.Client:
    """Create an httpx.Client backed by MockTransport that returns *xml_text*.

    If *requests* is provided, every incoming request is appended to that list
    so tests can inspect URLs, call counts, etc.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, text=xml_text)

    return httpx.Client(transport=httpx.MockTransport(_handler))


# =============================================================================
# Basic functionality
# =============================================================================


class TestSearchBasic:
    """Core search behavior: query -> list of PMIDs."""

    def test_simple_query_returns_pmids(self, mock_esearch_response: str) -> None:
        """search("CRISPR cancer") with mocked HTTP returns PMIDs as a list."""
        client = _make_search_client(mock_esearch_response)

        with patch("pm_tools.search.get_client", return_value=client):
            result = search("CRISPR cancer")

        assert result == ["12345", "67890", "11111"]

    def test_no_results_returns_empty_list(self, mock_esearch_empty_response: str) -> None:
        """Query with no matches returns empty list, not None or error."""
        client = _make_search_client(mock_esearch_empty_response)

        with patch("pm_tools.search.get_client", return_value=client):
            result = search("nonexistent_query_xyzzy")

        assert result == []



# =============================================================================
# Input validation
# =============================================================================


class TestSearchInputValidation:
    """Empty or missing query should raise an error."""

    def test_empty_query_raises_error(self) -> None:
        """search("") raises ValueError."""
        with pytest.raises(ValueError, match="[Qq]uery"):
            search("")

    def test_whitespace_only_query_raises_error(self) -> None:
        """search("   ") raises ValueError (whitespace-only is empty)."""
        with pytest.raises(ValueError, match="[Qq]uery"):
            search("   ")


# =============================================================================
# URL encoding of special characters
# =============================================================================


class TestSearchURLEncoding:
    """PubMed queries with special characters must not crash or corrupt the query."""

    @pytest.mark.parametrize(
        "query",
        [
            "asthma[MeSH Terms]",
            "(cancer OR tumor) AND treatment",
            "2020:2024[dp]",
            "2024/01/15[edat]",
            "cancer[ti] AND 2024[dp]",
        ],
        ids=["brackets", "parentheses", "colon", "slashes", "multi-field"],
    )
    def test_special_chars_reach_api(self, query: str, mock_esearch_response: str) -> None:
        """Queries with special characters are correctly encoded in the request URL."""
        captured: list[httpx.Request] = []
        client = _make_search_client(mock_esearch_response, requests=captured)

        with patch("pm_tools.search.get_client", return_value=client):
            result = search(query)

        # The search succeeded and returned PMIDs (not an error)
        assert result == ["12345", "67890", "11111"]

        # Verify the query actually appeared in the URL sent to the transport
        assert len(captured) == 1
        url = str(captured[0].url)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        assert "term" in params, f"Expected 'term' param in URL: {url}"
        assert params["term"][0] == query


# =============================================================================
# Error handling
# =============================================================================


class TestSearchErrorHandling:
    """Network and API errors should propagate as exceptions."""

    def test_http_error_raises_exception(self) -> None:
        """HTTP 500 from API should raise an exception."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Server Error")

        client = httpx.Client(transport=httpx.MockTransport(_handler))

        with (
            patch("pm_tools.search.get_client", return_value=client),
            pytest.raises((httpx.HTTPStatusError, RuntimeError)),
        ):
            search("cancer")

    def test_network_error_raises_exception(self) -> None:
        """Connection error should propagate."""

        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.Client(transport=httpx.MockTransport(_handler))

        with (
            patch("pm_tools.search.get_client", return_value=client),
            pytest.raises((httpx.ConnectError, ConnectionError, RuntimeError)),
        ):
            search("cancer")


# =============================================================================
# Search cache
# =============================================================================


class TestSearchCache:
    """search() caches results in .pm/cache/search/ when pm_dir is given."""

    def test_caches_results(self, mock_esearch_response: str, pm_dir: Path) -> None:
        """First call caches, second returns from cache with 0 API calls."""
        captured: list[httpx.Request] = []
        client = _make_search_client(mock_esearch_response, requests=captured)

        with patch("pm_tools.search.get_client", return_value=client):
            result1 = search("CRISPR cancer", pm_dir=pm_dir)
            assert len(captured) == 1

            result2 = search("CRISPR cancer", pm_dir=pm_dir)
            assert len(captured) == 1  # no additional API call

        assert result1 == result2



class TestSearchAudit:
    """search() logs to audit.jsonl when pm_dir is provided."""

    def test_logs_search_event(self, mock_esearch_response: str, pm_dir: Path) -> None:
        client = _make_search_client(mock_esearch_response)

        with patch("pm_tools.search.get_client", return_value=client):
            search("CRISPR cancer", pm_dir=pm_dir)

        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "search"
        assert event["db"] == "pubmed"
        assert event["query"] == "CRISPR cancer"
        assert event["count"] == 3  # mock returns 3 PMIDs
        assert event["cached"] is False

    def test_logs_cached_event_with_original_ts(
        self, mock_esearch_response: str, pm_dir: Path
    ) -> None:
        client = _make_search_client(mock_esearch_response)

        with patch("pm_tools.search.get_client", return_value=client):
            search("CRISPR", pm_dir=pm_dir)
            search("CRISPR", pm_dir=pm_dir)

        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        event2 = json.loads(lines[1])
        assert event2["cached"] is True
        assert "original_ts" in event2


# =============================================================================
# --max validation and -n alias (Phase 2)
# =============================================================================


class TestSearchMaxValidation:
    """Test --max rejects invalid values and -n alias works."""

    def test_max_zero_returns_exit_2(self) -> None:
        """--max 0 should be rejected by argparse (exit 2)."""
        from pm_tools.search import main

        result = main(["CRISPR", "--max", "0"])
        assert result == 2

    def test_max_negative_returns_exit_2(self) -> None:
        """--max -5 should be rejected by argparse (exit 2)."""
        from pm_tools.search import main

        result = main(["CRISPR", "--max", "-5"])
        assert result == 2

    def test_n_alias_works(self, mock_esearch_response: str) -> None:
        """-n 3 should be equivalent to --max 3 and return successfully."""
        from pm_tools.search import main

        client = _make_search_client(mock_esearch_response)

        with (
            patch("pm_tools.search.get_client", return_value=client),
            patch("pm_tools.search.find_pm_dir", return_value=None),
        ):
            result = main(["CRISPR", "-n", "3"])
            assert result == 0

    def test_max_non_integer_returns_exit_2(self) -> None:
        """--max abc should be rejected by argparse (exit 2)."""
        from pm_tools.search import main

        result = main(["CRISPR", "--max", "abc"])
        assert result == 2


# =============================================================================
# --verbose flag (Phase 3.2)
# =============================================================================


class TestSearchVerbose:
    """search -v prints server-side result count to stderr."""

    def test_verbose_shows_truncated_count(
        self,
        mock_esearch_truncated_response: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When total > returned, verbose shows 'Found N results, returning M'."""
        client = _make_search_client(mock_esearch_truncated_response)

        with patch("pm_tools.search.get_client", return_value=client):
            result = search("CRISPR", max_results=10, verbose=True)

        assert len(result) == 10
        captured = capsys.readouterr()
        assert "Found 5000 results, returning 10" in captured.err

    def test_verbose_shows_simple_count(
        self,
        mock_esearch_response: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When total == returned, verbose shows 'Found N results'."""
        client = _make_search_client(mock_esearch_response)

        with patch("pm_tools.search.get_client", return_value=client):
            result = search("CRISPR", verbose=True)

        assert len(result) == 3
        captured = capsys.readouterr()
        assert "Found 3 results" in captured.err
        # Should NOT contain "returning" when all results fit
        assert "returning" not in captured.err

    def test_verbose_no_searching_message(
        self,
        mock_esearch_response: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """search() no longer prints 'Searching PubMed for ...' (dedup with collect)."""
        client = _make_search_client(mock_esearch_response)

        with patch("pm_tools.search.get_client", return_value=client):
            search("CRISPR", verbose=True)

        captured = capsys.readouterr()
        assert "Searching PubMed for" not in captured.err

    def test_verbose_silent_on_cache_hit(
        self,
        mock_esearch_response: str,
        pm_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """On cache hit, verbose shows cache message, not result count."""
        client = _make_search_client(mock_esearch_response)

        with patch("pm_tools.search.get_client", return_value=client):
            # First call: fills cache
            search("CRISPR", pm_dir=pm_dir, verbose=True)
            capsys.readouterr()  # discard first call output

            # Second call: cache hit
            search("CRISPR", pm_dir=pm_dir, verbose=True)

        captured = capsys.readouterr()
        assert "cached" in captured.err
        assert "Found" not in captured.err

    def test_verbose_fallback_when_count_missing(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When <Count> is missing from response, falls back to len(pmids)."""
        # Response with no <Count> element
        xml_no_count = """<?xml version="1.0" encoding="UTF-8" ?>
<eSearchResult>
    <RetMax>2</RetMax>
    <IdList>
        <Id>111</Id>
        <Id>222</Id>
    </IdList>
</eSearchResult>"""
        client = _make_search_client(xml_no_count)

        with patch("pm_tools.search.get_client", return_value=client):
            result = search("test", verbose=True)

        assert len(result) == 2
        captured = capsys.readouterr()
        assert "Found 2 results" in captured.err
