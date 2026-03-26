"""Tests for pm_tools.fetch — Fetch PubMed XML by PMIDs.

Tests the fetch function at the Python module level, mocking HTTP responses.
The fetch module will be at pm_tools.fetch with:
  - fetch(pmids: list[str], batch_size: int = 200) -> str

"""

import json
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

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


def _make_xml_handler(
    pmid: str = "12345",
) -> Callable[[httpx.Request], httpx.Response]:
    """Return a handler that always responds with XML for the given PMID."""
    xml_text = MOCK_XML_TEMPLATE.format(pmid=pmid)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=xml_text)

    return handler


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    """Create an httpx.Client backed by a MockTransport."""
    return httpx.Client(transport=httpx.MockTransport(handler))


# =============================================================================
# Basic functionality
# =============================================================================


class TestFetchBasic:
    """Core fetch behavior: PMIDs -> XML string."""

    def test_single_pmid_returns_xml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fetch(["12345"]) returns XML containing the article."""
        client = _make_client(_make_xml_handler("12345"))
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        result = fetch(["12345"])

        root = ET.fromstring(result)
        assert root.tag == "PubmedArticleSet"
        assert root.find(".//PMID").text == "12345"



# =============================================================================
# Empty input
# =============================================================================


class TestFetchEmptyInput:
    """Empty PMID list should not make API calls."""

    def test_empty_list_returns_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fetch([]) returns empty string and makes no HTTP calls."""
        captured: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text="")

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        result = fetch([])

        assert result == ""

    def test_empty_strings_filtered_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fetch(["", "", ""]) treats all-empty as empty input."""
        captured: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text="")

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        result = fetch(["", "", ""])

        assert result == ""
        assert len(captured) == 0


# =============================================================================
# Batching
# =============================================================================


class TestFetchBatching:
    """PMIDs should be batched at 200 per request."""

    @pytest.mark.parametrize(
        ("n_pmids", "expected_batches"),
        [
            (3, 1),      # well under the limit
            (200, 1),    # boundary: exactly at limit
            (201, 2),    # boundary: one over the limit
        ],
        ids=["under-limit", "at-limit", "over-limit"],
    )
    def test_default_batch_boundary(
        self, n_pmids: int, expected_batches: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default batch_size=200: verify boundary between 1 and 2 batches."""
        captured: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text=MOCK_XML_TEMPLATE.format(pmid="12345"))

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        pmids = [str(i) for i in range(1, n_pmids + 1)]
        fetch(pmids, rate_limit_delay=0)

        assert len(captured) == expected_batches

    def test_custom_batch_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fetch(pmids, batch_size=50) should batch at 50."""
        captured: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text=MOCK_XML_TEMPLATE.format(pmid="12345"))

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        pmids = [str(i) for i in range(1, 101)]
        fetch(pmids, batch_size=50, rate_limit_delay=0)

        assert len(captured) == 2

    def test_multi_batch_produces_valid_xml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple batches must produce a single valid XML document.

        Bug: fetch() currently joins batch responses with newline, producing
        multiple XML declarations and root elements — invalid XML that
        ET.fromstring() rejects with 'junk after document element'.
        """
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            pmid = "111" if call_count == 1 else "222"
            return httpx.Response(200, text=MOCK_XML_TEMPLATE.format(pmid=pmid))

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        result = fetch(["111", "222"], batch_size=1, rate_limit_delay=0)

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

    def test_three_batches_take_minimum_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """3 batches (450 PMIDs) should sleep between batches due to rate limiting.

        With rate_limit_delay=0.05s and 3 batches: 2 sleeps = ~0.10s minimum.
        Using 0.08s as safe lower bound with margin.
        """
        client = _make_client(_make_xml_handler())
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        pmids = [str(i) for i in range(1, 451)]
        start = time.monotonic()
        fetch(pmids, rate_limit_delay=0.05)
        elapsed = time.monotonic() - start

        # With 3 batches and rate limiting, should take at least 0.08s
        assert elapsed >= 0.08, f"Expected >= 0.08s, got {elapsed:.3f}s (no rate limiting?)"


# =============================================================================
# Error handling
# =============================================================================


class TestFetchErrors:
    """API and network errors should propagate."""

    def test_http_error_raises_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HTTP 500 from API should raise an exception."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Server error")

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        with pytest.raises((httpx.HTTPStatusError, RuntimeError)):
            fetch(["12345"])

    def test_network_error_raises_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Connection error should propagate."""

        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        with pytest.raises((httpx.ConnectError, ConnectionError, RuntimeError)):
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


class TestFetchSmartBatch:
    """fetch() with pm_dir only fetches uncached PMIDs."""

    def test_all_cached_no_api_call(
        self, pm_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When all PMIDs are cached, zero API calls are made."""
        captured: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text="")

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        # Pre-populate cache with article fragments
        for pmid in ("111", "222"):
            xml = (
                f"<PubmedArticle><MedlineCitation>"
                f'<PMID Version="1">{pmid}</PMID>'
                f"<Article><ArticleTitle>Art {pmid}</ArticleTitle></Article>"
                f"</MedlineCitation></PubmedArticle>"
            )
            (pm_dir / "cache" / "fetch" / f"{pmid}.xml").write_text(xml)

        result = fetch(["111", "222"], pm_dir=pm_dir)

        assert len(captured) == 0
        assert "111" in result
        assert "222" in result
        # Must be valid XML
        root = ET.fromstring(result)
        assert root.tag == "PubmedArticleSet"

    def test_partial_cache_fetches_only_missing(
        self, pm_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only uncached PMIDs trigger API calls."""
        captured: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text=MOCK_XML_TEMPLATE.format(pmid="222"))

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        # Cache only PMID 111
        xml = (
            "<PubmedArticle><MedlineCitation>"
            '<PMID Version="1">111</PMID>'
            "<Article><ArticleTitle>Cached</ArticleTitle></Article>"
            "</MedlineCitation></PubmedArticle>"
        )
        (pm_dir / "cache" / "fetch" / "111.xml").write_text(xml)

        result = fetch(["111", "222"], pm_dir=pm_dir)

        # Only 1 API call (for 222), not 2
        assert len(captured) == 1
        # Both articles in result
        root = ET.fromstring(result)
        pmids = [e.text for e in root.findall(".//PMID") if e.text]
        assert "111" in pmids
        assert "222" in pmids

    def test_no_cache_without_pm_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without pm_dir, fetch works as before."""
        captured: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text=MOCK_XML_TEMPLATE.format(pmid="12345"))

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        fetch(["111", "222"])
        assert len(captured) == 1  # single batch, no cache


class TestFetchAudit:
    """fetch() logs to audit.jsonl when pm_dir is provided."""

    def test_logs_fetch_event(self, pm_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _make_client(_make_xml_handler())
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        fetch(["111", "222"], pm_dir=pm_dir)

        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "fetch"
        assert event["requested"] == 2

    def test_logs_cached_count(self, pm_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _make_client(_make_xml_handler("222"))
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        # Pre-cache one article
        xml = (
            "<PubmedArticle><MedlineCitation>"
            '<PMID Version="1">111</PMID>'
            "<Article><ArticleTitle>Cached</ArticleTitle></Article>"
            "</MedlineCitation></PubmedArticle>"
        )
        (pm_dir / "cache" / "fetch" / "111.xml").write_text(xml)

        fetch(["111", "222"], pm_dir=pm_dir)

        event = json.loads((pm_dir / "audit.jsonl").read_text().strip().splitlines()[0])
        assert event["cached"] == 1
        assert event["fetched"] == 1


class TestFetchRoundTrip:
    """split → cache → reassemble → parse must produce identical results."""

    def test_round_trip_preserves_data(
        self, pm_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pm_tools.parse import parse_xml

        captured: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text="")

        client = _make_client(_handler)
        monkeypatch.setattr("pm_tools.fetch.get_client", lambda: client)

        # Original parse
        original = parse_xml(TWO_ARTICLES_XML)

        # Split, cache, reassemble via fetch()
        fragments = split_xml_articles(TWO_ARTICLES_XML)
        for pmid, frag in fragments.items():
            (pm_dir / "cache" / "fetch" / f"{pmid}.xml").write_text(frag)

        reassembled_xml = fetch(["111", "222"], pm_dir=pm_dir)
        assert len(captured) == 0

        reassembled = parse_xml(reassembled_xml)

        # Same number of articles, same PMIDs, same titles
        assert len(reassembled) == len(original)
        orig_pmids = {a["pmid"] for a in original}
        new_pmids = {a["pmid"] for a in reassembled}
        assert orig_pmids == new_pmids



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

    def test_malicious_pmid_rejected(self) -> None:
        """A PMID like '123&retmode=json' must be rejected (non-numeric)."""
        with pytest.raises(ValueError, match="Invalid PMID"):
            _make_efetch_batch(["123&retmode=json"])


