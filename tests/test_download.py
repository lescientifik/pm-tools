"""Tests for pm_tools.download — find PDF sources and download them.

RED phase: tests that validate download behavior and drive new features.

Core tests validate existing functionality. Tests for unimplemented features
(concurrent downloads, download manifest, file verification) will fail,
driving new development.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pm_tools.download import download_pdfs, find_pdf_sources, pmc_lookup, unpaywall_lookup

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
# FTP → HTTPS conversion in pmc_lookup
# ---------------------------------------------------------------------------


class TestPmcLookupFtpUrls:
    def test_ftp_url_converted_to_https(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PMC OA responses with ftp:// URLs are converted to https://."""
        ftp_response = """\
<?xml version="1.0" encoding="UTF-8"?>
<OA>
  <records>
    <record id="PMC12345" citation="Some Citation" license="CC BY">
      <link format="pdf" href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/ab/cd/PMC12345.pdf" />
    </record>
  </records>
</OA>
"""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, text=ftp_response)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.download.get_http_client", lambda: client)

        result = pmc_lookup("PMC12345")
        assert result is not None
        assert result.startswith("https://")
        assert "ftp.ncbi.nlm.nih.gov" in result


# ---------------------------------------------------------------------------
# Verbose progress in main()
# ---------------------------------------------------------------------------


class TestDownloadVerboseProgress:
    def test_verbose_shows_per_article_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With -v, stderr contains per-article PMID and status."""
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

        exit_code = download_main(["--output-dir", str(output_dir), "-v"])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "99999" in captured.err


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
