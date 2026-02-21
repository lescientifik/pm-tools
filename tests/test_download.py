"""Tests for pm_tools.download — find PDF sources and download them.

RED phase: tests that validate download behavior and drive new features.

Core tests validate existing functionality. Tests for unimplemented features
(concurrent downloads, download manifest, file verification) will fail,
driving new development.
"""

from __future__ import annotations

import io
import json
import logging
import tarfile
from pathlib import Path

import httpx
import pytest

from pm_tools.download import (
    PmcResult,
    _extract_pdf_from_tgz,
    download_pdfs,
    find_pdf_sources,
    pmc_lookup,
    unpaywall_lookup,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _art(
    pmid: str = "1",
    pmcid: str | None = None,
    doi: str | None = None,
    title: str = "Title",
) -> dict:
    """Minimal article dict with optional PMC / DOI identifiers."""
    d: dict = {"pmid": pmid, "title": title}
    if pmcid is not None:
        d["pmcid"] = pmcid
    if doi is not None:
        d["doi"] = doi
    return d


_FAKE_PDF = b"%PDF-1.4 fake pdf content for testing"


def _make_tgz(files: dict[str, bytes]) -> bytes:
    """Create an in-memory tar.gz archive from {name: content} dict."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fake HTTP responses
# ---------------------------------------------------------------------------


_PMC_OA_RESPONSE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<OA>
  <records>
    <record id="PMC12345" citation="Some Citation" license="CC BY">
      <link format="pdf" href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/ab/cd/PMC12345.pdf" />
    </record>
  </records>
</OA>
"""

_UNPAYWALL_RESPONSE = {
    "doi": "10.1234/test",
    "is_oa": True,
    "best_oa_location": {
        "url_for_pdf": "https://example.com/paper.pdf",
        "host_type": "publisher",
        "license": "cc-by",
    },
}


def _make_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Phase 9.0a: PmcResult dataclass
# ---------------------------------------------------------------------------


class TestPmcResult:
    def test_pmc_result_has_url_and_format(self) -> None:
        """PmcResult can be instantiated with url and format fields."""
        result = PmcResult(url="https://example.com/paper.pdf", format="pdf")
        assert result.url == "https://example.com/paper.pdf"
        assert result.format == "pdf"

    def test_pmc_result_tgz_format(self) -> None:
        """PmcResult supports tgz format."""
        result = PmcResult(url="https://example.com/archive.tar.gz", format="tgz")
        assert result.url == "https://example.com/archive.tar.gz"
        assert result.format == "tgz"


# ---------------------------------------------------------------------------
# Phase 9.1: _extract_pdf_from_tgz (pure function)
# ---------------------------------------------------------------------------


class TestExtractPdfFromTgz:
    def test_extracts_pdf_from_subdirectory(self) -> None:
        """PDF in a subdirectory (typical PMC structure) is found."""
        archive = _make_tgz({"PMC12345/paper.pdf": _FAKE_PDF})
        result = _extract_pdf_from_tgz(archive)
        assert result == _FAKE_PDF

    def test_prefers_pdf_matching_pmcid(self) -> None:
        """When multiple PDFs exist, prefer the one matching PMCID."""
        supplement = b"%PDF-1.4 supplement"
        main_pdf = b"%PDF-1.4 main article (larger)"
        archive = _make_tgz(
            {
                "PMC12345/supplement_s1.pdf": supplement,
                "PMC12345/PMC12345_article.pdf": main_pdf,
            }
        )
        result = _extract_pdf_from_tgz(archive, pmcid="PMC12345")
        # Should prefer the one with PMC12345 in the name
        assert result == main_pdf

    def test_multiple_pdfs_no_pmcid_returns_largest(self) -> None:
        """Without PMCID hint, return the largest PDF."""
        small = b"%PDF-1.4 small"
        large = b"%PDF-1.4 large article content" * 10
        archive = _make_tgz(
            {
                "dir/small.pdf": small,
                "dir/large.pdf": large,
            }
        )
        result = _extract_pdf_from_tgz(archive)
        assert result == large

    def test_no_pdf_returns_none(self) -> None:
        """Archive with only XML/images returns None."""
        archive = _make_tgz(
            {
                "PMC12345/paper.nxml": b"<article>...</article>",
                "PMC12345/figure1.jpg": b"\xff\xd8\xff\xe0 fake jpg",
            }
        )
        result = _extract_pdf_from_tgz(archive)
        assert result is None

    def test_invalid_data_returns_none(self) -> None:
        """Random bytes (not a valid tgz) returns None."""
        result = _extract_pdf_from_tgz(b"this is not a tar.gz file at all")
        assert result is None

    def test_html_soft_404_returns_none(self) -> None:
        """HTML response (soft 404) returns None."""
        result = _extract_pdf_from_tgz(b"<html><body>Access Denied</body></html>")
        assert result is None

    def test_empty_archive_returns_none(self) -> None:
        """Empty tar.gz archive returns None."""
        archive = _make_tgz({})
        result = _extract_pdf_from_tgz(archive)
        assert result is None

    def test_empty_pdf_returns_none(self) -> None:
        """A 0-byte PDF member returns None (not b'')."""
        archive = _make_tgz({"PMC12345/paper.pdf": b""})
        result = _extract_pdf_from_tgz(archive)
        assert result is None

    def test_oversized_member_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Members with size > MAX_PDF_MEMBER_SIZE are skipped."""
        import pm_tools.download as dl

        # Temporarily lower the limit so our test PDF exceeds it
        monkeypatch.setattr(dl, "MAX_PDF_MEMBER_SIZE", 5)

        archive = _make_tgz({"PMC12345/paper.pdf": _FAKE_PDF})
        result = _extract_pdf_from_tgz(archive)
        # _FAKE_PDF is ~40 bytes > 5 byte limit → skipped → None
        assert result is None


# ---------------------------------------------------------------------------
# find_pdf_sources
# ---------------------------------------------------------------------------


class TestFindPdfSourcesEmpty:
    def test_empty_input_returns_empty(self) -> None:
        result = find_pdf_sources([])
        assert result == []

    def test_no_identifiers_reports_no_source(self) -> None:
        """Article with neither pmcid nor doi -> no source found."""
        articles = [_art(pmid="1")]
        result = find_pdf_sources(articles)
        no_source = [r for r in result if r.get("source") is None]
        assert len(no_source) == 1
        assert no_source[0]["pmid"] == "1"


class TestFindPdfSourcesPMC:
    def test_pmcid_uses_pmc_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Article with pmcid should query PMC OA service."""

        def _handler(request: httpx.Request) -> httpx.Response:
            if "pmc/utils/oa" in str(request.url):
                return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [_art(pmid="1", pmcid="PMC12345")]
        result = find_pdf_sources(articles)

        pmc_sources = [r for r in result if r.get("source") == "pmc"]
        assert len(pmc_sources) == 1
        assert "PMC12345" in pmc_sources[0]["url"]


class TestFindPdfSourcesUnpaywall:
    def test_doi_uses_unpaywall_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Article with doi (no pmcid) should query Unpaywall."""

        def _handler(request: httpx.Request) -> httpx.Response:
            if "api.unpaywall.org" in str(request.url):
                return httpx.Response(status_code=200, json=_UNPAYWALL_RESPONSE)
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [_art(pmid="1", doi="10.1234/test")]
        result = find_pdf_sources(articles, email="test@example.com")

        unpaywall = [r for r in result if r.get("source") == "unpaywall"]
        assert len(unpaywall) == 1
        assert unpaywall[0]["url"] == "https://example.com/paper.pdf"


# ---------------------------------------------------------------------------
# download_pdfs
# ---------------------------------------------------------------------------


class TestDownloadPdfs:
    def test_creates_output_directory(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "pdfs" / "nested"
        assert not output_dir.exists()

        sources: list[dict] = []
        result = download_pdfs(sources, output_dir)

        assert output_dir.exists()
        assert result["downloaded"] == 0

    def test_skips_existing_files_without_overwrite(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a PDF already exists, it should be skipped (not re-downloaded)."""
        output_dir = tmp_path / "pdfs"
        output_dir.mkdir()
        existing = output_dir / "12345678.pdf"
        existing.write_bytes(b"%PDF-1.4 fake content")

        sources = [{"pmid": "12345678", "source": "pmc", "url": "https://example.com/paper.pdf"}]

        request_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(status_code=200, content=b"%PDF-1.4 new content")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = download_pdfs(sources, output_dir, overwrite=False)

        assert result["skipped"] == 1
        assert result["downloaded"] == 0
        assert request_count == 0, "Should not make HTTP request for existing file"

    def test_downloads_pdf_to_output_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful download should write the PDF file."""
        output_dir = tmp_path / "pdfs"
        pdf_content = b"%PDF-1.4 actual pdf bytes"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, content=pdf_content)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "99999", "source": "unpaywall", "url": "https://example.com/99.pdf"}]
        result = download_pdfs(sources, output_dir)

        assert result["downloaded"] == 1
        saved = output_dir / "99999.pdf"
        assert saved.exists()
        assert saved.read_bytes() == pdf_content

    def test_overwrite_replaces_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With overwrite=True, existing files should be re-downloaded."""
        output_dir = tmp_path / "pdfs"
        output_dir.mkdir()
        existing = output_dir / "12345678.pdf"
        existing.write_bytes(b"old content")

        new_content = b"%PDF-1.4 updated content"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, content=new_content)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "12345678", "source": "pmc", "url": "https://example.com/paper.pdf"}]
        result = download_pdfs(sources, output_dir, overwrite=True)

        assert result["downloaded"] == 1
        assert result["skipped"] == 0
        assert existing.read_bytes() == new_content


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestDownloadErrors:
    def test_no_input_raises_or_returns_empty(self) -> None:
        """find_pdf_sources with empty list should return empty, not crash."""
        result = find_pdf_sources([])
        assert result == []

    def test_http_error_counted_as_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 500 response should be counted as failed, not raise."""
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=500, text="Internal Server Error")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "1", "source": "pmc", "url": "https://example.com/fail.pdf"}]
        result = download_pdfs(sources, output_dir)

        assert result["failed"] == 1
        assert result["downloaded"] == 0

    def test_retry_on_transient_503_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 503 response should be retried before counting as failed."""
        output_dir = tmp_path / "pdfs"
        attempt_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                return httpx.Response(status_code=503, text="Service Unavailable")
            return httpx.Response(status_code=200, content=b"%PDF-1.4 success after retry")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "1", "source": "pmc", "url": "https://example.com/retry.pdf"}]
        result = download_pdfs(sources, output_dir)

        assert result["downloaded"] == 1, "Should succeed after retrying transient 503"
        assert attempt_count == 3, "Should have made 3 attempts (2 retries + 1 success)"


# ---------------------------------------------------------------------------
# pmc_lookup error handling
# ---------------------------------------------------------------------------


class TestPmcLookupErrors:
    def test_network_error_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ConnectError during PMC lookup returns None instead of raising."""

        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC12345")
        assert result is None

    def test_timeout_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ReadTimeout during PMC lookup returns None instead of raising."""

        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Read timed out")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC12345")
        assert result is None

    def test_http_500_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HTTP 500 from PMC OA service returns None."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=500, text="Internal Server Error")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC12345")
        assert result is None


# ---------------------------------------------------------------------------
# Phase 8.1: pmc_lookup logging
# ---------------------------------------------------------------------------


class TestPmcLookupLogging:
    def test_logs_warning_on_http_error_status(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """pmc_lookup logs WARNING with status code when HTTP != 200."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=500, text="Server Error")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            pmc_lookup("PMC99999")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "500" in warnings[0].message
        assert "PMC99999" in warnings[0].message

    def test_logs_warning_on_api_error_in_response(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """pmc_lookup logs WARNING when response contains <error."""
        error_xml = (
            '<?xml version="1.0"?><OA>'
            '<error code="idIsNotValid">id parameter is not valid</error>'
            "</OA>"
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=error_xml)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            pmc_lookup("PMC99999")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "PMC99999" in warnings[0].message

    def test_logs_warning_on_parse_error(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """pmc_lookup logs WARNING when XML parsing fails."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text="not xml at all <<<")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            pmc_lookup("PMC99999")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "PMC99999" in warnings[0].message

    def test_logs_debug_with_url(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """pmc_lookup logs DEBUG with the URL being queried."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            pmc_lookup("PMC12345")

        debug_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_msgs) >= 1
        assert "pmc/utils/oa" in debug_msgs[0].message

    def test_logs_warning_on_network_error(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """pmc_lookup logs WARNING on network errors (ConnectError, etc.)."""

        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            pmc_lookup("PMC12345")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "PMC12345" in warnings[0].message


# ---------------------------------------------------------------------------
# unpaywall_lookup error handling
# ---------------------------------------------------------------------------


class TestUnpaywallLookupErrors:
    def test_network_error_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ConnectError during Unpaywall lookup returns None."""

        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = unpaywall_lookup("10.1234/test", "test@example.com")
        assert result is None

    def test_non_json_response_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HTML response instead of JSON returns None."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                text="<html>Error</html>",
                headers={"content-type": "text/html"},
            )

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = unpaywall_lookup("10.1234/test", "test@example.com")
        assert result is None

    def test_http_404_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HTTP 404 from Unpaywall returns None."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=404, text="Not Found")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = unpaywall_lookup("10.1234/test", "test@example.com")
        assert result is None


# ---------------------------------------------------------------------------
# Phase 8.2: unpaywall_lookup logging
# ---------------------------------------------------------------------------


class TestUnpaywallLookupLogging:
    def test_logs_warning_on_http_error_status(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """unpaywall_lookup logs WARNING with status code when HTTP != 200."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=404, text="Not Found")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            unpaywall_lookup("10.1234/test", "test@example.com")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "404" in warnings[0].message
        assert "10.1234/test" in warnings[0].message

    def test_logs_warning_on_json_decode_error(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """unpaywall_lookup logs WARNING when JSON parsing fails."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                text="<html>Error</html>",
                headers={"content-type": "text/html"},
            )

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            unpaywall_lookup("10.1234/test", "test@example.com")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "10.1234/test" in warnings[0].message

    def test_logs_warning_on_network_error(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """unpaywall_lookup logs WARNING on network errors."""

        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            unpaywall_lookup("10.1234/test", "test@example.com")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "10.1234/test" in warnings[0].message

    def test_logs_debug_with_url(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """unpaywall_lookup logs DEBUG with the URL being queried."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, json=_UNPAYWALL_RESPONSE)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            unpaywall_lookup("10.1234/test", "test@example.com")

        debug_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_msgs) >= 1
        assert "api.unpaywall.org" in debug_msgs[0].message

    def test_logs_debug_not_open_access(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """unpaywall_lookup logs DEBUG when article is not open access."""
        closed_response = {"doi": "10.1234/test", "is_oa": False}

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, json=closed_response)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            unpaywall_lookup("10.1234/test", "test@example.com")

        debug_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("not open access" in r.message for r in debug_msgs)


# ---------------------------------------------------------------------------
# find_pdf_sources error resilience
# ---------------------------------------------------------------------------


class TestFindPdfSourcesErrorResilience:
    def test_pmc_error_does_not_stop_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If first article's PMC lookup crashes, second article is still processed."""
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [
            _art(pmid="1", pmcid="PMC11111"),
            _art(pmid="2", pmcid="PMC12345"),
        ]
        result = find_pdf_sources(articles)

        # First should fail gracefully, second should succeed
        sources_by_pmid = {r["pmid"]: r for r in result}
        assert len(result) == 2
        assert sources_by_pmid["1"]["source"] is None
        assert sources_by_pmid["2"]["source"] == "pmc"


# ---------------------------------------------------------------------------
# Phase 8.3: find_pdf_sources logging
# ---------------------------------------------------------------------------


class TestFindPdfSourcesLogging:
    def test_logs_warning_on_exception(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """find_pdf_sources logs WARNING when an unexpected exception occurs."""

        def _boom(pmcid: str) -> str | None:
            raise RuntimeError("unexpected crash")

        monkeypatch.setattr("pm_tools.download.pmc_lookup", _boom)

        articles = [_art(pmid="1", pmcid="PMC11111")]
        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            result = find_pdf_sources(articles)

        # Should not crash — returns source: None
        assert result[0]["source"] is None

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "1" in warnings[0].message  # PMID in message

    def test_logs_debug_reason_no_source(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """find_pdf_sources logs DEBUG explaining why no source was found."""
        # Article with no pmcid and no doi — should log the reason
        articles = [_art(pmid="42")]
        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            find_pdf_sources(articles, pmc_only=True)

        debug_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("42" in r.message for r in debug_msgs)


# ---------------------------------------------------------------------------
# Phase 9.0b: pmc_lookup returns PmcResult + tgz support
# ---------------------------------------------------------------------------


_PMC_OA_TGZ_ONLY_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<OA><records>"
    '<record id="PMC9273392" citation="X" license="CC BY">'
    '<link format="tgz"'
    ' href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/46/ea/PMC9273392.tar.gz" />'
    "</record>"
    "</records></OA>"
)

_PMC_OA_BOTH_FORMATS_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<OA><records>"
    '<record id="PMC3531190" citation="X" license="CC BY">'
    '<link format="tgz"'
    ' href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/ab/cd/PMC3531190.tar.gz" />'
    '<link format="pdf"'
    ' href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/ab/cd/PMC3531190.pdf" />'
    "</record>"
    "</records></OA>"
)

_PMC_OA_NO_LINKS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<OA>
  <records>
    <record id="PMC99999" citation="Some Citation" license="CC BY">
    </record>
  </records>
</OA>
"""


class TestPmcLookupReturnType:
    def test_pdf_format_returns_pmc_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """pmc_lookup with PDF link returns PmcResult(format='pdf')."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC12345")
        assert result is not None
        assert isinstance(result, PmcResult)
        assert result.format == "pdf"
        assert "PMC12345" in result.url

    def test_tgz_only_returns_pmc_result_tgz(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """pmc_lookup with tgz-only link returns PmcResult(format='tgz')."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=_PMC_OA_TGZ_ONLY_XML)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC9273392")
        assert result is not None
        assert isinstance(result, PmcResult)
        assert result.format == "tgz"
        assert "PMC9273392" in result.url

    def test_both_formats_prefers_pdf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When both pdf and tgz are available, prefer pdf."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=_PMC_OA_BOTH_FORMATS_XML)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC3531190")
        assert result is not None
        assert result.format == "pdf"

    def test_no_links_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """pmc_lookup with no links returns None."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=_PMC_OA_NO_LINKS_XML)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC99999")
        assert result is None

    def test_ftp_url_converted_to_https_pdf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FTP URLs are converted to HTTPS for pdf links."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC12345")
        assert result is not None
        assert result.url.startswith("https://")
        assert "ftp.ncbi.nlm.nih.gov" in result.url

    def test_ftp_url_converted_to_https_tgz(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FTP URLs are converted to HTTPS for tgz links."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=_PMC_OA_TGZ_ONLY_XML)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC9273392")
        assert result is not None
        assert result.url.startswith("https://")
        assert "ftp.ncbi.nlm.nih.gov" in result.url

    def test_logs_debug_with_format(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """pmc_lookup logs DEBUG indicating the format found."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=_PMC_OA_TGZ_ONLY_XML)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            pmc_lookup("PMC9273392")

        debug_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("tgz" in r.message for r in debug_msgs)


# ---------------------------------------------------------------------------
# Phase 9.0c: find_pdf_sources propagates pmc_format
# ---------------------------------------------------------------------------


class TestFindPdfSourcesPmcFormat:
    def test_pmc_format_pdf_when_pdf_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Source dict contains pmc_format='pdf' when PDF direct link available."""

        def _handler(request: httpx.Request) -> httpx.Response:
            if "pmc/utils/oa" in str(request.url):
                return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [_art(pmid="1", pmcid="PMC12345")]
        result = find_pdf_sources(articles)

        pmc = [r for r in result if r["source"] == "pmc"]
        assert len(pmc) == 1
        assert pmc[0]["pmc_format"] == "pdf"

    def test_pmc_format_tgz_when_tgz_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Source dict contains pmc_format='tgz' when only tgz available."""

        def _handler(request: httpx.Request) -> httpx.Response:
            if "pmc/utils/oa" in str(request.url):
                return httpx.Response(status_code=200, text=_PMC_OA_TGZ_ONLY_XML)
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [_art(pmid="1", pmcid="PMC9273392")]
        result = find_pdf_sources(articles)

        pmc = [r for r in result if r["source"] == "pmc"]
        assert len(pmc) == 1
        assert pmc[0]["pmc_format"] == "tgz"

    def test_no_pmc_format_for_unpaywall(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unpaywall sources don't have pmc_format key."""

        def _handler(request: httpx.Request) -> httpx.Response:
            if "api.unpaywall.org" in str(request.url):
                return httpx.Response(status_code=200, json=_UNPAYWALL_RESPONSE)
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [_art(pmid="1", doi="10.1234/test")]
        result = find_pdf_sources(articles, email="test@example.com")

        unpaywall = [r for r in result if r["source"] == "unpaywall"]
        assert len(unpaywall) == 1
        assert "pmc_format" not in unpaywall[0]

    def test_no_pmc_format_for_no_source(self) -> None:
        """Articles with no source don't have pmc_format key."""
        articles = [_art(pmid="1")]
        result = find_pdf_sources(articles)

        no_source = [r for r in result if r["source"] is None]
        assert len(no_source) == 1
        assert "pmc_format" not in no_source[0]


# ---------------------------------------------------------------------------
# Phase 8.5: main() logging configuration + integration
# ---------------------------------------------------------------------------


class TestDownloadVerboseProgress:
    """Migrated from capsys/_verbose_progress to caplog/logger (issue #8)."""

    def test_verbose_shows_per_article_status(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """With -v, stderr contains per-article PMID and status via logger."""
        import io

        from pm_tools.download import main as download_main

        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)
            if "ftp.ncbi.nlm.nih.gov" in url or "example.com" in url:
                return httpx.Response(status_code=200, content=b"%PDF-1.4 content")
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)
        monkeypatch.setattr("pm_tools.cache.find_pm_dir", lambda: None)

        # Simulate JSONL input via stdin
        jsonl_input = '{"pmid":"99999","pmcid":"PMC12345","doi":"10.1234/test"}\n'
        monkeypatch.setattr("sys.stdin", io.StringIO(jsonl_input))

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            exit_code = download_main(["--output-dir", str(output_dir), "-v"])

        assert exit_code == 0
        captured = capsys.readouterr()
        # Summary always on stderr; DEBUG logs contain PMC lookup URL
        assert "Downloaded: 1" in captured.err
        assert any("PMC lookup:" in r.message for r in caplog.records)


class TestMainLoggingConfig:
    def test_warnings_on_stderr_without_verbose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Without --verbose, WARNING-level logs still appear."""
        import io

        from pm_tools.download import main as download_main

        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                return httpx.Response(status_code=403, text="Forbidden")
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)
        monkeypatch.setattr("pm_tools.cache.find_pm_dir", lambda: None)

        jsonl_input = '{"pmid":"11111","pmcid":"PMC99999","doi":""}\n'
        monkeypatch.setattr("sys.stdin", io.StringIO(jsonl_input))

        with caplog.at_level(logging.WARNING, logger="pm_tools.download"):
            download_main(["--output-dir", str(output_dir), "--pmc-only"])

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1

    def test_debug_hidden_without_verbose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Without --verbose, DEBUG-level logs should NOT appear on stderr."""
        import io

        from pm_tools.download import main as download_main

        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)
            if "ftp.ncbi.nlm.nih.gov" in url or "example.com" in url:
                return httpx.Response(status_code=200, content=b"%PDF-1.4 content")
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)
        monkeypatch.setattr("pm_tools.cache.find_pm_dir", lambda: None)

        jsonl_input = '{"pmid":"99999","pmcid":"PMC12345","doi":"10.1234/test"}\n'
        monkeypatch.setattr("sys.stdin", io.StringIO(jsonl_input))

        # Run without -v: logger level should be WARNING
        download_main(["--output-dir", str(output_dir)])

        captured = capsys.readouterr()
        # DEBUG messages like "PMC lookup:" should NOT be in stderr
        assert "PMC lookup:" not in captured.err

    def test_debug_shown_with_verbose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """With --verbose, DEBUG-level logs appear."""
        import io

        from pm_tools.download import main as download_main

        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)
            if "ftp.ncbi.nlm.nih.gov" in url or "example.com" in url:
                return httpx.Response(status_code=200, content=b"%PDF-1.4 content")
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)
        monkeypatch.setattr("pm_tools.cache.find_pm_dir", lambda: None)

        jsonl_input = '{"pmid":"99999","pmcid":"PMC12345","doi":"10.1234/test"}\n'
        monkeypatch.setattr("sys.stdin", io.StringIO(jsonl_input))

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            download_main(["--output-dir", str(output_dir), "-v"])

        debug_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("PMC lookup:" in r.message for r in debug_msgs)

    def test_summary_always_on_stderr(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Summary line always appears on stderr, even without --verbose."""
        import io

        from pm_tools.download import main as download_main

        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)
            if "ftp.ncbi.nlm.nih.gov" in url or "example.com" in url:
                return httpx.Response(status_code=200, content=b"%PDF-1.4 content")
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)
        monkeypatch.setattr("pm_tools.cache.find_pm_dir", lambda: None)

        jsonl_input = '{"pmid":"99999","pmcid":"PMC12345","doi":"10.1234/test"}\n'
        monkeypatch.setattr("sys.stdin", io.StringIO(jsonl_input))

        download_main(["--output-dir", str(output_dir)])

        captured = capsys.readouterr()
        assert "Downloaded:" in captured.err
        assert "Failed:" in captured.err

    def test_issue_8_repro_diagnostics(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Repro case from issue #8: failing PMIDs must produce diagnostics."""
        import io

        from pm_tools.download import main as download_main

        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                if "PMC11111" in url:
                    # First PMID has a PMC source, but download returns 403
                    return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)
                # Second PMID has no PMC source
                return httpx.Response(status_code=200, text='<OA><error code="idIsNotValid"/></OA>')
            if "ftp.ncbi.nlm.nih.gov" in url:
                return httpx.Response(status_code=403, text="Forbidden")
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)
        monkeypatch.setattr("pm_tools.cache.find_pm_dir", lambda: None)

        # Two PMIDs: one with PMC source (will 403), one without any source
        jsonl_lines = (
            '{"pmid":"30623617","pmcid":"PMC11111","doi":""}\n'
            '{"pmid":"35350465","pmcid":"","doi":""}\n'
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(jsonl_lines))

        with caplog.at_level(logging.WARNING, logger="pm_tools.download"):
            exit_code = download_main(["--output-dir", str(output_dir), "--pmc-only"])

        captured = capsys.readouterr()

        # Must explain WHY each PMID failed
        all_output = caplog.text + captured.err
        assert "403" in all_output, "Should mention HTTP 403"
        assert "Downloaded: 0" in captured.err
        assert "Failed: 2" in captured.err
        assert exit_code == 2  # No PDFs downloaded


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------


class TestDownloadProgress:
    def test_progress_callback_called_for_each_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        output_dir = tmp_path / "pdfs"
        progress_events: list[dict] = []

        def on_progress(event: dict) -> None:
            progress_events.append(event)

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, content=b"%PDF-1.4 content")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [
            {"pmid": "1", "source": "pmc", "url": "https://example.com/1.pdf"},
            {"pmid": "2", "source": "pmc", "url": "https://example.com/2.pdf"},
        ]
        download_pdfs(sources, output_dir, progress_callback=on_progress)

        assert len(progress_events) == 2, "Should call progress_callback for each source"
        assert progress_events[0]["pmid"] == "1"
        assert progress_events[1]["pmid"] == "2"


# ---------------------------------------------------------------------------
# Phase 8.4: download_pdfs logging
# ---------------------------------------------------------------------------


class TestDownloadPdfsLogging:
    def test_logs_warning_with_http_status_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """download_pdfs logs WARNING with actual HTTP status code on failure."""
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=403, text="Forbidden")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "123", "source": "pmc", "url": "https://example.com/1.pdf"}]
        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            download_pdfs(sources, output_dir)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "403" in warnings[0].message
        assert "123" in warnings[0].message

    def test_logs_warning_with_url_and_pmid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """download_pdfs logs WARNING with URL and PMID for each failure."""
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=500, text="Error")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "456", "source": "pmc", "url": "https://example.com/paper.pdf"}]
        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            download_pdfs(sources, output_dir)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "456" in warnings[0].message
        assert "example.com" in warnings[0].message

    def test_logs_warning_on_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """download_pdfs logs WARNING with exception message on HTTPError/OSError."""
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Read timed out")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "789", "source": "pmc", "url": "https://example.com/1.pdf"}]
        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            download_pdfs(sources, output_dir)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "789" in warnings[0].message

    def test_logs_warning_on_empty_response(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """download_pdfs logs WARNING when response body is empty."""
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, content=b"")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "321", "source": "pmc", "url": "https://example.com/empty.pdf"}]
        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            download_pdfs(sources, output_dir)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "321" in warnings[0].message
        assert "empty" in warnings[0].message.lower()

    def test_logs_warning_on_retry_exhaustion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """download_pdfs logs WARNING when all retries are exhausted (3x 503)."""
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=503, text="Service Unavailable")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "654", "source": "pmc", "url": "https://example.com/retry.pdf"}]
        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            download_pdfs(sources, output_dir)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "654" in warnings[0].message
        assert "503" in warnings[0].message

    def test_callback_includes_status_code_and_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """progress_callback event dict includes status_code and url on failure."""
        output_dir = tmp_path / "pdfs"
        events: list[dict] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=403, text="Forbidden")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "1", "source": "pmc", "url": "https://example.com/1.pdf"}]
        download_pdfs(sources, output_dir, progress_callback=events.append)

        assert len(events) == 1
        assert events[0]["status"] == "failed"
        assert events[0]["status_code"] == 403
        assert events[0]["url"] == "https://example.com/1.pdf"
        # Backward compat: original keys still present
        assert events[0]["pmid"] == "1"
        assert events[0]["reason"] == "http_error"

    def test_logs_warning_no_url(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """download_pdfs logs WARNING when source has no URL."""
        output_dir = tmp_path / "pdfs"

        sources = [{"pmid": "999", "source": None, "url": None}]
        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            download_pdfs(sources, output_dir)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "999" in warnings[0].message


# ---------------------------------------------------------------------------
# Integration: JSONL input with mixed identifiers
# ---------------------------------------------------------------------------


class TestFindSourcesMixed:
    def test_accepts_articles_with_pmid_pmcid_doi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """find_pdf_sources should handle a mix of identifier types."""

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "pmc/utils/oa" in url:
                return httpx.Response(status_code=200, text=_PMC_OA_RESPONSE_XML)
            if "api.unpaywall.org" in url:
                return httpx.Response(status_code=200, json=_UNPAYWALL_RESPONSE)
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        articles = [
            _art(pmid="1", pmcid="PMC12345"),
            _art(pmid="2", doi="10.1234/test"),
            _art(pmid="3"),
        ]
        result = find_pdf_sources(articles, email="test@example.com")

        assert len(result) == 3
        sources_by_pmid = {r["pmid"]: r for r in result}

        assert sources_by_pmid["1"]["source"] == "pmc"
        assert sources_by_pmid["2"]["source"] == "unpaywall"
        assert sources_by_pmid["3"]["source"] is None


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def _make_pm_dir(tmp_path: Path) -> Path:
    pm = tmp_path / ".pm"
    pm.mkdir()
    for sub in ("search", "fetch", "cite", "download"):
        (pm / "cache" / sub).mkdir(parents=True)
    (pm / "audit.jsonl").write_text("")
    return pm


class TestDownloadAudit:
    """download_pdfs() logs to audit.jsonl when pm_dir is provided."""

    def test_logs_download_event(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pm_dir = _make_pm_dir(tmp_path)
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, content=b"%PDF-1.4 content")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [
            {
                "pmid": "111",
                "source": "pmc",
                "url": "https://example.com/1.pdf",
            },
            {
                "pmid": "222",
                "source": "pmc",
                "url": "https://example.com/2.pdf",
            },
        ]
        download_pdfs(sources, output_dir, pm_dir=pm_dir)

        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "download"
        assert event["downloaded"] == 2
        assert event["failed"] == 0

    def test_logs_mixed_results(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pm_dir = _make_pm_dir(tmp_path)
        output_dir = tmp_path / "pdfs"

        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(status_code=200, content=b"%PDF-1.4 content")
            return httpx.Response(status_code=500, text="Error")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [
            {
                "pmid": "111",
                "source": "pmc",
                "url": "https://example.com/1.pdf",
            },
            {
                "pmid": "222",
                "source": "pmc",
                "url": "https://example.com/2.pdf",
            },
        ]
        download_pdfs(sources, output_dir, pm_dir=pm_dir)

        event = json.loads((pm_dir / "audit.jsonl").read_text().strip().splitlines()[0])
        assert event["downloaded"] == 1
        assert event["failed"] == 1

    def test_no_audit_without_pm_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without pm_dir, download works as before."""
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, content=b"%PDF-1.4 content")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [
            {
                "pmid": "111",
                "source": "pmc",
                "url": "https://example.com/1.pdf",
            },
        ]
        result = download_pdfs(sources, output_dir)
        assert result["downloaded"] == 1


# ---------------------------------------------------------------------------
# Phase 8.0: Logger infrastructure
# ---------------------------------------------------------------------------


class TestLoggerSetup:
    def test_download_module_has_logger(self) -> None:
        """The download module should have a logger named 'pm_tools.download'."""
        import pm_tools.download as mod

        assert hasattr(mod, "logger")
        assert mod.logger.name == "pm_tools.download"

    def test_caplog_captures_download_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        """Validate that caplog can capture logs from pm_tools.download."""
        import pm_tools.download as mod

        with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
            mod.logger.debug("caplog test message")
        assert any("caplog test message" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Unimplemented features (RED phase)
# ---------------------------------------------------------------------------


class TestDownloadManifest:
    """download_pdfs should produce a manifest JSONL file listing all downloaded files.

    Not yet implemented -- drives adding download tracking.
    """

    def test_writes_manifest_jsonl(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import json

        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, content=b"%PDF-1.4 content")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [
            {"pmid": "1", "source": "pmc", "url": "https://example.com/1.pdf"},
            {"pmid": "2", "source": "unpaywall", "url": "https://example.com/2.pdf"},
        ]
        download_pdfs(sources, output_dir, manifest=True)

        manifest_path = output_dir / "manifest.jsonl"
        assert manifest_path.exists(), "Should create manifest.jsonl in output directory"

        entries = [json.loads(line) for line in manifest_path.read_text().splitlines()]
        assert len(entries) == 2
        assert entries[0]["pmid"] == "1"
        assert entries[0]["source"] == "pmc"
        assert "path" in entries[0]


class TestDownloadVerify:
    """download_pdfs should verify downloaded files are valid PDFs.

    Not yet implemented -- drives adding content verification.
    """

    def test_non_pdf_content_counted_as_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the response is HTML instead of PDF, it should be counted as failed."""
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                content=b"<html><body>Access Denied</body></html>",
                headers={"content-type": "text/html"},
            )

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [{"pmid": "1", "source": "pmc", "url": "https://example.com/1.pdf"}]
        result = download_pdfs(sources, output_dir, verify_pdf=True)

        assert result["failed"] == 1, (
            "HTML response should be detected as non-PDF and counted as failed"
        )
        assert result["downloaded"] == 0
        # Should not have written the file
        assert not (output_dir / "1.pdf").exists(), "Non-PDF content should not be saved"


class TestConcurrentDownload:
    """download_pdfs should support concurrent downloads with max_concurrent parameter.

    Not yet implemented -- drives adding async/concurrent download support.
    """

    def test_concurrent_downloads(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        output_dir = tmp_path / "pdfs"

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, content=b"%PDF-1.4 content")

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        sources = [
            {"pmid": str(i), "source": "pmc", "url": f"https://example.com/{i}.pdf"}
            for i in range(10)
        ]
        result = download_pdfs(sources, output_dir, max_concurrent=4)

        assert result["downloaded"] == 10, "All 10 PDFs should be downloaded"
