"""Tests for pm_tools.fetch — Fetch PubMed XML by PMIDs.

Tests the fetch function at the Python module level, mocking HTTP responses.
The fetch module will be at pm_tools.fetch with:
  - fetch(pmids: list[str], batch_size: int = 200) -> str

All tests are written RED-first: they MUST fail until the module is implemented.
"""

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from pm_tools.fetch import fetch

MOCK_XML_TEMPLATE = """<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN"
 "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation>
        <PMID Version="1">{pmid}</PMID>
        <Article>
            <ArticleTitle>Article {pmid}</ArticleTitle>
        </Article>
    </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""


def _make_mock_response(pmid: str = "12345") -> MagicMock:
    """Create a mock httpx.Response with valid XML."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = 200
    mock.text = MOCK_XML_TEMPLATE.format(pmid=pmid)
    mock.raise_for_status = MagicMock()
    return mock


# =============================================================================
# Basic functionality
# =============================================================================


class TestFetchBasic:
    """Core fetch behavior: PMIDs -> XML string."""

    def test_single_pmid_returns_xml(self) -> None:
        """fetch(["12345"]) returns XML containing the article."""
        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response("12345")):
            result = fetch(["12345"])

        assert "PubmedArticleSet" in result
        assert "12345" in result

    def test_returns_string(self) -> None:
        """Return type is str (XML text)."""
        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()):
            result = fetch(["12345"])

        assert isinstance(result, str)

    def test_single_pmid_calls_efetch(self) -> None:
        """HTTP request targets efetch.fcgi endpoint with correct params."""
        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()) as mock_get:
            fetch(["12345"])

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        url_str = str(call_args)

        # Should call efetch.fcgi
        assert "efetch.fcgi" in url_str or "efetch" in url_str

    def test_efetch_uses_correct_parameters(self) -> None:
        """Request includes db=pubmed, rettype=abstract, retmode=xml."""
        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()) as mock_get:
            fetch(["12345"])

        call_args = mock_get.call_args
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)

        # db=pubmed
        assert params.get("db") == "pubmed" or "db=pubmed" in url_str
        # rettype=abstract
        assert params.get("rettype") == "abstract" or "rettype=abstract" in url_str
        # retmode=xml
        assert params.get("retmode") == "xml" or "retmode=xml" in url_str

    def test_pmids_sent_as_comma_separated(self) -> None:
        """Multiple PMIDs are joined with commas in the id parameter."""
        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()) as mock_get:
            fetch(["111", "222", "333"])

        call_args = mock_get.call_args
        params = call_args[1].get("params", {}) if call_args[1] else {}
        url_str = str(call_args)

        assert (
            params.get("id") == "111,222,333"
            or "id=111,222,333" in url_str
            or "id=111%2C222%2C333" in url_str
        )


# =============================================================================
# Empty input
# =============================================================================


class TestFetchEmptyInput:
    """Empty PMID list should not make API calls."""

    def test_empty_list_returns_empty_string(self) -> None:
        """fetch([]) returns empty string and makes no HTTP calls."""
        with patch("pm_tools.fetch.httpx.get") as mock_get:
            result = fetch([])

        assert result == ""
        mock_get.assert_not_called()

    def test_empty_strings_filtered_out(self) -> None:
        """fetch(["", "", ""]) treats all-empty as empty input."""
        with patch("pm_tools.fetch.httpx.get") as mock_get:
            result = fetch(["", "", ""])

        assert result == ""
        mock_get.assert_not_called()


# =============================================================================
# Batching
# =============================================================================


class TestFetchBatching:
    """PMIDs should be batched at 200 per request."""

    def test_small_list_single_batch(self) -> None:
        """3 PMIDs should result in exactly 1 API call."""
        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()) as mock_get:
            fetch(["111", "222", "333"])

        assert mock_get.call_count == 1

    def test_200_pmids_single_batch(self) -> None:
        """Exactly 200 PMIDs should be 1 batch."""
        pmids = [str(i) for i in range(1, 201)]

        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()) as mock_get:
            fetch(pmids)

        assert mock_get.call_count == 1

    def test_201_pmids_two_batches(self) -> None:
        """201 PMIDs should split into 2 batches (200 + 1)."""
        pmids = [str(i) for i in range(1, 202)]

        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()) as mock_get:
            fetch(pmids)

        assert mock_get.call_count == 2

    def test_250_pmids_two_batches(self) -> None:
        """250 PMIDs should split into 2 batches (200 + 50)."""
        pmids = [str(i) for i in range(1, 251)]

        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()) as mock_get:
            fetch(pmids)

        assert mock_get.call_count == 2

    def test_450_pmids_three_batches(self) -> None:
        """450 PMIDs should split into 3 batches (200 + 200 + 50)."""
        pmids = [str(i) for i in range(1, 451)]

        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()) as mock_get:
            fetch(pmids)

        assert mock_get.call_count == 3

    def test_custom_batch_size(self) -> None:
        """fetch(pmids, batch_size=50) should batch at 50."""
        pmids = [str(i) for i in range(1, 101)]

        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()) as mock_get:
            fetch(pmids, batch_size=50)

        assert mock_get.call_count == 2

    def test_batches_combine_xml_output(self) -> None:
        """Multiple batches should produce combined XML output."""
        pmids = [str(i) for i in range(1, 251)]

        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()):
            result = fetch(pmids)

        # Should contain XML content (not be empty)
        assert "PubmedArticle" in result


# =============================================================================
# Rate limiting
# =============================================================================


class TestFetchRateLimiting:
    """Rate limiting: max 3 requests per second (no API key)."""

    def test_three_batches_take_minimum_time(self) -> None:
        """3 batches (450 PMIDs) should take at least 0.5s due to rate limiting.

        Rate limit = 3 req/sec = ~0.33s between requests.
        For 3 requests: need 2 delays = ~0.66s minimum, using 0.5s as safe margin.
        """
        pmids = [str(i) for i in range(1, 451)]

        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()):
            start = time.monotonic()
            fetch(pmids)
            elapsed = time.monotonic() - start

        # With 3 batches and rate limiting, should take at least 0.5s
        assert elapsed >= 0.5, f"Expected >= 0.5s, got {elapsed:.3f}s (no rate limiting?)"


# =============================================================================
# Error handling
# =============================================================================


class TestFetchErrors:
    """API and network errors should propagate."""

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
            patch("pm_tools.fetch.httpx.get", return_value=mock_response),
            pytest.raises((httpx.HTTPStatusError, RuntimeError)),
        ):
            fetch(["12345"])

    def test_network_error_raises_exception(self) -> None:
        """Connection error should propagate."""
        with (
            patch(
                "pm_tools.fetch.httpx.get",
                side_effect=httpx.ConnectError("Connection refused"),
            ),
            pytest.raises((httpx.ConnectError, ConnectionError, RuntimeError)),
        ):
            fetch(["12345"])
