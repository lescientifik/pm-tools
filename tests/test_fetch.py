"""Tests for pm_tools.fetch — Fetch PubMed XML by PMIDs.

Tests the fetch function at the Python module level, mocking HTTP responses.
The fetch module will be at pm_tools.fetch with:
  - fetch(pmids: list[str], batch_size: int = 200) -> str

All tests are written RED-first: they MUST fail until the module is implemented.
"""

import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from pm_tools.fetch import _make_efetch_batch, fetch, split_xml_articles

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


def _mock_client_for(mock_response: MagicMock) -> MagicMock:
    """Create a mock HTTP client whose .get() returns the given response."""
    client = MagicMock()
    client.get.return_value = mock_response
    return client


# =============================================================================
# Basic functionality
# =============================================================================


class TestFetchBasic:
    """Core fetch behavior: PMIDs -> XML string."""

    def test_single_pmid_returns_xml(self) -> None:
        """fetch(["12345"]) returns XML containing the article."""
        mock_client = _mock_client_for(_make_mock_response("12345"))

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            result = fetch(["12345"])

        assert "PubmedArticleSet" in result
        assert "12345" in result

    def test_returns_string(self) -> None:
        """Return type is str (XML text)."""
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            result = fetch(["12345"])

        assert isinstance(result, str)

    def test_single_pmid_calls_efetch(self) -> None:
        """HTTP request targets efetch.fcgi endpoint with correct params."""
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(["12345"])

        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        url_str = str(call_args)

        # Should call efetch.fcgi
        assert "efetch.fcgi" in url_str or "efetch" in url_str

    def test_efetch_uses_correct_parameters(self) -> None:
        """Request includes db=pubmed, rettype=abstract, retmode=xml."""
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(["12345"])

        call_args = mock_client.get.call_args
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
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(["111", "222", "333"])

        call_args = mock_client.get.call_args
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
        mock_client = MagicMock()

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            result = fetch([])

        assert result == ""
        mock_client.get.assert_not_called()

    def test_empty_strings_filtered_out(self) -> None:
        """fetch(["", "", ""]) treats all-empty as empty input."""
        mock_client = MagicMock()

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            result = fetch(["", "", ""])

        assert result == ""
        mock_client.get.assert_not_called()


# =============================================================================
# Batching
# =============================================================================


class TestFetchBatching:
    """PMIDs should be batched at 200 per request."""

    def test_small_list_single_batch(self) -> None:
        """3 PMIDs should result in exactly 1 API call."""
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(["111", "222", "333"])

        assert mock_client.get.call_count == 1

    def test_200_pmids_single_batch(self) -> None:
        """Exactly 200 PMIDs should be 1 batch."""
        pmids = [str(i) for i in range(1, 201)]
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(pmids)

        assert mock_client.get.call_count == 1

    def test_201_pmids_two_batches(self) -> None:
        """201 PMIDs should split into 2 batches (200 + 1)."""
        pmids = [str(i) for i in range(1, 202)]
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(pmids)

        assert mock_client.get.call_count == 2

    def test_250_pmids_two_batches(self) -> None:
        """250 PMIDs should split into 2 batches (200 + 50)."""
        pmids = [str(i) for i in range(1, 251)]
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(pmids)

        assert mock_client.get.call_count == 2

    def test_450_pmids_three_batches(self) -> None:
        """450 PMIDs should split into 3 batches (200 + 200 + 50)."""
        pmids = [str(i) for i in range(1, 451)]
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(pmids)

        assert mock_client.get.call_count == 3

    def test_custom_batch_size(self) -> None:
        """fetch(pmids, batch_size=50) should batch at 50."""
        pmids = [str(i) for i in range(1, 101)]
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(pmids, batch_size=50)

        assert mock_client.get.call_count == 2

    def test_batches_combine_xml_output(self) -> None:
        """Multiple batches should produce combined XML output."""
        pmids = [str(i) for i in range(1, 251)]
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
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

        mock_client = MagicMock()
        mock_client.get.side_effect = batch_responses

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
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
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
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

        mock_client = _mock_client_for(mock_response)

        with (
            patch("pm_tools.fetch.get_client", return_value=mock_client),
            pytest.raises((httpx.HTTPStatusError, RuntimeError)),
        ):
            fetch(["12345"])

    def test_network_error_raises_exception(self) -> None:
        """Connection error should propagate."""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with (
            patch("pm_tools.fetch.get_client", return_value=mock_client),
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
    """fetch() with pm_dir only fetches uncached PMIDs."""

    def test_all_cached_no_api_call(self, tmp_path: Path) -> None:
        """When all PMIDs are cached, zero API calls are made."""
        pm_dir = _make_pm_dir(tmp_path)

        # Pre-populate cache with article fragments
        for pmid in ("111", "222"):
            xml = (
                f"<PubmedArticle><MedlineCitation>"
                f'<PMID Version="1">{pmid}</PMID>'
                f"<Article><ArticleTitle>Art {pmid}</ArticleTitle></Article>"
                f"</MedlineCitation></PubmedArticle>"
            )
            (pm_dir / "cache" / "fetch" / f"{pmid}.xml").write_text(xml)

        mock_client = MagicMock()

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            result = fetch(["111", "222"], pm_dir=pm_dir)

        mock_client.get.assert_not_called()
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
            "<PubmedArticle><MedlineCitation>"
            '<PMID Version="1">111</PMID>'
            "<Article><ArticleTitle>Cached</ArticleTitle></Article>"
            "</MedlineCitation></PubmedArticle>"
        )
        (pm_dir / "cache" / "fetch" / "111.xml").write_text(xml)

        # Mock API returns PMID 222
        mock_client = _mock_client_for(_make_mock_response("222"))

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            result = fetch(["111", "222"], pm_dir=pm_dir)

        # Only 1 API call (for 222), not 2
        assert mock_client.get.call_count == 1
        # Both articles in result
        root = ET.fromstring(result)
        pmids = [e.text for e in root.findall(".//PMID") if e.text]
        assert "111" in pmids
        assert "222" in pmids

    def test_no_cache_without_pm_dir(self) -> None:
        """Without pm_dir, fetch works as before."""
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(["111", "222"])
        assert mock_client.get.call_count == 1  # single batch, no cache


class TestFetchAudit:
    """fetch() logs to audit.jsonl when pm_dir is provided."""

    def test_logs_fetch_event(self, tmp_path: Path) -> None:
        pm_dir = _make_pm_dir(tmp_path)
        mock_client = _mock_client_for(_make_mock_response())

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(["111", "222"], pm_dir=pm_dir)

        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "fetch"
        assert event["requested"] == 2

    def test_logs_cached_count(self, tmp_path: Path) -> None:
        pm_dir = _make_pm_dir(tmp_path)

        # Pre-cache one article
        xml = (
            "<PubmedArticle><MedlineCitation>"
            '<PMID Version="1">111</PMID>'
            "<Article><ArticleTitle>Cached</ArticleTitle></Article>"
            "</MedlineCitation></PubmedArticle>"
        )
        (pm_dir / "cache" / "fetch" / "111.xml").write_text(xml)

        mock_client = _mock_client_for(_make_mock_response("222"))

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            fetch(["111", "222"], pm_dir=pm_dir)

        event = json.loads((pm_dir / "audit.jsonl").read_text().strip().splitlines()[0])
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

        mock_client = MagicMock()

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            reassembled_xml = fetch(["111", "222"], pm_dir=pm_dir)
        mock_client.get.assert_not_called()

        reassembled = parse_xml(reassembled_xml)

        # Same number of articles, same PMIDs, same titles
        assert len(reassembled) == len(original)
        orig_pmids = {a["pmid"] for a in original}
        new_pmids = {a["pmid"] for a in reassembled}
        assert orig_pmids == new_pmids


# =============================================================================
# Positional PMIDs in CLI
# =============================================================================


class TestFetchPositionalPmids:
    """Test that fetch CLI accepts positional PMIDs (same pattern as cite)."""

    @patch("pm_tools.cache.find_pm_dir", return_value=None)
    @patch("pm_tools.fetch.fetch")
    def test_positional_pmid(self, mock_fetch_fn: MagicMock, mock_find: MagicMock) -> None:
        """fetch.main(["41873355"]) should produce output."""
        from pm_tools.fetch import main

        mock_fetch_fn.return_value = "<xml/>"
        result = main(["41873355"])
        assert result == 0
        mock_fetch_fn.assert_called_once()
        assert "41873355" in mock_fetch_fn.call_args[0][0]

    @patch("pm_tools.cache.find_pm_dir", return_value=None)
    @patch("pm_tools.fetch.fetch")
    def test_multiple_positional_pmids(
        self, mock_fetch_fn: MagicMock, mock_find: MagicMock,
    ) -> None:
        """Multiple positional PMIDs all passed to fetch()."""
        from pm_tools.fetch import main

        mock_fetch_fn.return_value = "<xml/>"
        result = main(["111", "222", "333"])
        assert result == 0
        assert mock_fetch_fn.call_args[0][0] == ["111", "222", "333"]

    @patch("pm_tools.cache.find_pm_dir", return_value=None)
    @patch("pm_tools.fetch.fetch")
    def test_positional_with_verbose(self, mock_fetch_fn: MagicMock, mock_find: MagicMock) -> None:
        """Positional PMIDs work with -v flag."""
        from pm_tools.fetch import main

        mock_fetch_fn.return_value = "<xml/>"
        result = main(["41873355", "-v"])
        assert result == 0
        assert "41873355" in mock_fetch_fn.call_args[0][0]

    @patch("pm_tools.cache.find_pm_dir", return_value=None)
    @patch("pm_tools.fetch.fetch")
    def test_stdin_fallback_when_no_positional(
        self,
        mock_fetch_fn: MagicMock,
        mock_find: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Stdin is read when no positional args and stdin is not a TTY."""
        import io

        from pm_tools.fetch import main

        mock_fetch_fn.return_value = "<xml/>"
        monkeypatch.setattr("sys.stdin", io.StringIO("12345\n67890\n"))
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        result = main([])
        assert result == 0
        mock_fetch_fn.assert_called_once()
        assert mock_fetch_fn.call_args[0][0] == ["12345", "67890"]


# =============================================================================
# PMID validation at entry point
# =============================================================================


class TestFetchPmidValidation:
    """fetch.main() rejects non-numeric PMIDs (path traversal, PMC IDs)."""

    def test_path_traversal_rejected(self) -> None:
        """fetch.main() with a path traversal PMID returns error code 1."""
        from pm_tools.fetch import main

        result = main(["../../etc/passwd"])
        assert result == 1

    def test_mixed_valid_and_invalid_rejected(self) -> None:
        """A single bad PMID in a batch causes rejection."""
        from pm_tools.fetch import main

        result = main(["12345678", "../../etc/passwd"])
        assert result == 1


# =============================================================================
# URL parameter encoding (v0.3.1 phase 2.2)
# =============================================================================


class TestFetchUrlEncoding:
    """_make_efetch_batch() must produce safe, well-formed URLs."""

    def test_batch_url_has_correct_id_param(self) -> None:
        """_make_efetch_batch(["123", "456"]) encodes id=123,456 in the URL."""
        mock_client = _mock_client_for(_make_mock_response("123"))

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            _make_efetch_batch(["123", "456"])

        url = mock_client.get.call_args[0][0]
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        assert params["id"] == ["123,456"]

    def test_batch_url_has_correct_retmode(self) -> None:
        """_make_efetch_batch() always sets retmode=xml."""
        mock_client = _mock_client_for(_make_mock_response("123"))

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            _make_efetch_batch(["123"])

        url = mock_client.get.call_args[0][0]
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        assert params["retmode"] == ["xml"]

    def test_malicious_pmid_rejected(self) -> None:
        """A PMID like '123&retmode=json' must be rejected (non-numeric)."""
        with pytest.raises(ValueError, match="Invalid PMID"):
            _make_efetch_batch(["123&retmode=json"])

    def test_whitespace_pmid_stripped_and_validated(self) -> None:
        """PMIDs with leading/trailing whitespace are stripped before validation."""
        mock_client = _mock_client_for(_make_mock_response("123"))

        with patch("pm_tools.fetch.get_client", return_value=mock_client):
            _make_efetch_batch(["  123  ", "456"])

        url = mock_client.get.call_args[0][0]
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        assert params["id"] == ["123,456"]
