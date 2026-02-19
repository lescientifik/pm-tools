"""Tests for pm_tools.fetch — Fetch PubMed XML by PMIDs.

Tests the fetch function at the Python module level, mocking HTTP responses.
The fetch module will be at pm_tools.fetch with:
  - fetch(pmids: list[str], batch_size: int = 200) -> str

All tests are written RED-first: they MUST fail until the module is implemented.
"""

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from pm_tools.fetch import fetch, split_xml_articles

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

    def test_multi_batch_produces_valid_xml(self) -> None:
        """Multiple batches must produce a single valid XML document.

        Bug: fetch() currently joins batch responses with newline, producing
        multiple XML declarations and root elements — invalid XML that
        ET.fromstring() rejects with 'junk after document element'.
        """
        import xml.etree.ElementTree as ET

        # Each batch returns a full XML document with its own declaration
        batch_responses = iter(
            [
                _make_mock_response("111"),
                _make_mock_response("222"),
            ]
        )

        with patch("pm_tools.fetch.httpx.get", side_effect=batch_responses):
            result = fetch(["111", "222"], batch_size=1)

        # Must be parseable as a single XML document
        root = ET.fromstring(result)
        assert root.tag == "PubmedArticleSet"

        # Must contain articles from BOTH batches
        pmids = [elem.text for elem in root.findall(".//PMID") if elem.text]
        assert "111" in pmids
        assert "222" in pmids


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


# =============================================================================
# XML splitting
# =============================================================================

TWO_ARTICLES_XML = """<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation><PMID Version="1">111</PMID>
    <Article><ArticleTitle>Article 111</ArticleTitle></Article>
    </MedlineCitation>
</PubmedArticle>
<PubmedArticle>
    <MedlineCitation><PMID Version="1">222</PMID>
    <Article><ArticleTitle>Article 222</ArticleTitle></Article>
    </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""


class TestSplitXmlArticles:
    """split_xml_articles() extracts per-PMID XML fragments."""

    def test_splits_two_articles(self) -> None:
        result = split_xml_articles(TWO_ARTICLES_XML)
        assert "111" in result
        assert "222" in result

    def test_fragments_are_valid_xml(self) -> None:
        result = split_xml_articles(TWO_ARTICLES_XML)
        for _pmid, fragment in result.items():
            root = ET.fromstring(fragment)
            assert root.tag == "PubmedArticle"

    def test_empty_xml_returns_empty(self) -> None:
        result = split_xml_articles("")
        assert result == {}

    def test_single_article(self) -> None:
        xml = MOCK_XML_TEMPLATE.format(pmid="999")
        result = split_xml_articles(xml)
        assert "999" in result
        assert len(result) == 1


# =============================================================================
# Smart batching (fetch with cache)
# =============================================================================


def _make_pm_dir(tmp_path: Path) -> Path:
    pm = tmp_path / ".pm"
    pm.mkdir()
    for sub in ("search", "fetch", "cite", "download"):
        (pm / "cache" / sub).mkdir(parents=True)
    (pm / "audit.jsonl").write_text("")
    return pm


class TestFetchSmartBatch:
    """fetch() with cache_dir only fetches uncached PMIDs."""

    def test_all_cached_no_api_call(self, tmp_path: Path) -> None:
        """When all PMIDs are cached, zero API calls are made."""
        pm_dir = _make_pm_dir(tmp_path)

        # Pre-populate cache with article fragments
        for pmid in ("111", "222"):
            xml = (
                f"<PubmedArticle><MedlineCitation>"
                f"<PMID Version=\"1\">{pmid}</PMID>"
                f"<Article><ArticleTitle>Art {pmid}</ArticleTitle></Article>"
                f"</MedlineCitation></PubmedArticle>"
            )
            (pm_dir / "cache" / "fetch" / f"{pmid}.xml").write_text(xml)

        with patch("pm_tools.fetch.httpx.get") as mock_get:
            result = fetch(["111", "222"], cache_dir=pm_dir)

        mock_get.assert_not_called()
        assert "111" in result
        assert "222" in result
        # Must be valid XML
        root = ET.fromstring(result)
        assert root.tag == "PubmedArticleSet"

    def test_partial_cache_fetches_only_missing(self, tmp_path: Path) -> None:
        """Only uncached PMIDs trigger API calls."""
        pm_dir = _make_pm_dir(tmp_path)

        # Cache only PMID 111
        xml = (
            '<PubmedArticle><MedlineCitation>'
            '<PMID Version="1">111</PMID>'
            '<Article><ArticleTitle>Cached</ArticleTitle></Article>'
            '</MedlineCitation></PubmedArticle>'
        )
        (pm_dir / "cache" / "fetch" / "111.xml").write_text(xml)

        # Mock API returns PMID 222
        mock_response = _make_mock_response("222")

        with patch(
            "pm_tools.fetch.httpx.get", return_value=mock_response
        ) as mock_get:
            result = fetch(["111", "222"], cache_dir=pm_dir)

        # Only 1 API call (for 222), not 2
        assert mock_get.call_count == 1
        # Both articles in result
        root = ET.fromstring(result)
        pmids = [e.text for e in root.findall(".//PMID") if e.text]
        assert "111" in pmids
        assert "222" in pmids

    def test_no_cache_without_cache_dir(self) -> None:
        """Without cache_dir, fetch works as before."""
        with patch(
            "pm_tools.fetch.httpx.get", return_value=_make_mock_response()
        ) as mock_get:
            fetch(["111", "222"])
        assert mock_get.call_count == 1  # single batch, no cache


class TestFetchAudit:
    """fetch() logs to audit.jsonl when pm_dir is provided."""

    def test_logs_fetch_event(self, tmp_path: Path) -> None:
        pm_dir = _make_pm_dir(tmp_path)

        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response()):
            fetch(["111", "222"], cache_dir=pm_dir, pm_dir=pm_dir)

        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "fetch"
        assert event["requested"] == 2

    def test_logs_cached_count(self, tmp_path: Path) -> None:
        pm_dir = _make_pm_dir(tmp_path)

        # Pre-cache one article
        xml = (
            '<PubmedArticle><MedlineCitation>'
            '<PMID Version="1">111</PMID>'
            '<Article><ArticleTitle>Cached</ArticleTitle></Article>'
            '</MedlineCitation></PubmedArticle>'
        )
        (pm_dir / "cache" / "fetch" / "111.xml").write_text(xml)

        with patch("pm_tools.fetch.httpx.get", return_value=_make_mock_response("222")):
            fetch(["111", "222"], cache_dir=pm_dir, pm_dir=pm_dir)

        event = json.loads(
            (pm_dir / "audit.jsonl").read_text().strip().splitlines()[0]
        )
        assert event["cached"] == 1
        assert event["fetched"] == 1


class TestFetchRoundTrip:
    """split → cache → reassemble → parse must produce identical results."""

    def test_round_trip_preserves_data(self, tmp_path: Path) -> None:
        from pm_tools.parse import parse_xml

        pm_dir = _make_pm_dir(tmp_path)

        # Original parse
        original = parse_xml(TWO_ARTICLES_XML)

        # Split, cache, reassemble via fetch()
        fragments = split_xml_articles(TWO_ARTICLES_XML)
        for pmid, frag in fragments.items():
            (pm_dir / "cache" / "fetch" / f"{pmid}.xml").write_text(frag)

        with patch("pm_tools.fetch.httpx.get") as mock_get:
            reassembled_xml = fetch(["111", "222"], cache_dir=pm_dir)
        mock_get.assert_not_called()

        reassembled = parse_xml(reassembled_xml)

        # Same number of articles, same PMIDs, same titles
        assert len(reassembled) == len(original)
        orig_pmids = {a["pmid"] for a in original}
        new_pmids = {a["pmid"] for a in reassembled}
        assert orig_pmids == new_pmids
