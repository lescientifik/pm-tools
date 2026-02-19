"""Tests for pm_tools.search — PubMed search returning PMIDs.

Tests the search function at the Python module level, mocking HTTP responses.
The search module will be at pm_tools.search with:
  - search(query: str, max_results: int = 10000) -> list[str]

All tests are written RED-first: they MUST fail until the module is implemented.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from pm_tools.search import search

# =============================================================================
# Basic functionality
# =============================================================================


class TestSearchBasic:
    """Core search behavior: query -> list of PMIDs."""

    def test_simple_query_returns_pmids(self, mock_esearch_response: str) -> None:
        """search("CRISPR cancer") with mocked HTTP returns PMIDs as a list."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            result = search("CRISPR cancer")

        assert result == ["12345", "67890", "11111"]
        # Verify the API was called
        mock_get.assert_called_once()

    def test_returns_list_of_strings(self, mock_esearch_response: str) -> None:
        """Return type is list[str], not list[int] or other."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response):
            result = search("cancer")

        assert isinstance(result, list)
        assert all(isinstance(pmid, str) for pmid in result)

    def test_no_results_returns_empty_list(self, mock_esearch_empty_response: str) -> None:
        """Query with no matches returns empty list, not None or error."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_empty_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response):
            result = search("nonexistent_query_xyzzy")

        assert result == []


# =============================================================================
# API call parameters
# =============================================================================


class TestSearchAPIParameters:
    """Verify correct E-utilities API parameters are sent."""

    def test_calls_esearch_endpoint(self, mock_esearch_response: str) -> None:
        """HTTP request targets esearch.fcgi endpoint."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            search("cancer")

        call_args = mock_get.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        # The URL should contain esearch.fcgi (could be in URL or params)
        assert "esearch.fcgi" in str(url) or "esearch" in str(call_args)

    def test_uses_pubmed_database(self, mock_esearch_response: str) -> None:
        """Request includes db=pubmed parameter."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            search("cancer")

        call_args = mock_get.call_args
        # Check params dict or URL string for db=pubmed
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)
        assert params.get("db") == "pubmed" or "db=pubmed" in url_str

    def test_default_max_results_is_10000(self, mock_esearch_response: str) -> None:
        """Default retmax should be 10000."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            search("cancer")

        call_args = mock_get.call_args
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)
        assert params.get("retmax") in (10000, "10000") or "retmax=10000" in url_str

    def test_max_results_parameter_passed(self, mock_esearch_response: str) -> None:
        """search(query, max_results=100) passes retmax=100 to the API."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            search("cancer", max_results=100)

        call_args = mock_get.call_args
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)
        assert params.get("retmax") in (100, "100") or "retmax=100" in url_str


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
    """PubMed queries use brackets, parens, colons, slashes that need encoding."""

    def test_encodes_square_brackets(self, mock_esearch_response: str) -> None:
        """Square brackets in field tags like [MeSH Terms] are URL-encoded."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            search("asthma[MeSH Terms]")

        # The query should be passed to the API; httpx may encode params automatically,
        # but the term should contain the original query text
        call_args = mock_get.call_args
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)
        # Either the params dict has the raw query (httpx encodes it)
        # or the URL contains the percent-encoded form
        assert (
            params.get("term") == "asthma[MeSH Terms]"
            or "%5BMeSH" in url_str
            or "asthma[MeSH" in url_str
        )

    def test_encodes_parentheses_in_boolean_queries(self, mock_esearch_response: str) -> None:
        """Parentheses in boolean grouping are handled correctly."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            search("(cancer OR tumor) AND treatment")

        call_args = mock_get.call_args
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)
        assert (
            params.get("term") == "(cancer OR tumor) AND treatment"
            or "%28cancer" in url_str
            or "(cancer" in url_str
        )

    def test_encodes_colon_in_date_ranges(self, mock_esearch_response: str) -> None:
        """Colons in date range queries like 2020:2024[dp] are encoded."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            search("2020:2024[dp]")

        call_args = mock_get.call_args
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)
        assert params.get("term") == "2020:2024[dp]" or "%3A" in url_str or "2020:2024" in url_str

    def test_encodes_slashes_in_date_queries(self, mock_esearch_response: str) -> None:
        """Slashes in date queries like 2024/01/15[edat] are encoded."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            search("2024/01/15[edat]")

        call_args = mock_get.call_args
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)
        assert (
            params.get("term") == "2024/01/15[edat]" or "%2F" in url_str or "2024/01/15" in url_str
        )

    def test_encodes_multiple_field_tags(self, mock_esearch_response: str) -> None:
        """Multiple field tags: cancer[ti] AND 2024[dp]."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch("pm_tools.search.httpx.get", return_value=mock_response) as mock_get:
            search("cancer[ti] AND 2024[dp]")

        call_args = mock_get.call_args
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)
        assert (
            params.get("term") == "cancer[ti] AND 2024[dp]"
            or ("%5Bti%5D" in url_str and "%5Bdp%5D" in url_str)
            or ("cancer[ti]" in url_str and "2024[dp]" in url_str)
        )


# =============================================================================
# Error handling
# =============================================================================


class TestSearchErrorHandling:
    """Network and API errors should propagate as exceptions."""

    def test_http_error_raises_exception(self) -> None:
        """HTTP 500 from API should raise an exception."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server error",
                request=MagicMock(),
                response=mock_response,
            )
        )

        with (
            patch("pm_tools.search.httpx.get", return_value=mock_response),
            pytest.raises((httpx.HTTPStatusError, RuntimeError)),
        ):
            search("cancer")

    def test_network_error_raises_exception(self) -> None:
        """Connection error should propagate."""
        with (
            patch(
                "pm_tools.search.httpx.get",
                side_effect=httpx.ConnectError("Connection refused"),
            ),
            pytest.raises((httpx.ConnectError, ConnectionError, RuntimeError)),
        ):
            search("cancer")
