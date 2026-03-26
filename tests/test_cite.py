"""Tests for pm_tools.cite — fetch CSL-JSON citation data for PMIDs.

Tests for core cite functionality validate the existing get_http_client()
pattern and error recovery. Cache test drives the audit/cache feature.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pm_tools.cite import _make_cite_batch, cite

# ---------------------------------------------------------------------------
# Helpers -- fake API responses
# ---------------------------------------------------------------------------

# The NCBI Citation Exporter returns CSL-JSON directly (list or single object).
_CSL_SINGLE = {
    "type": "article-journal",
    "PMID": "12345678",
    "title": "A groundbreaking study on CRISPR.",
    "container-title": "Nature",
    "DOI": "10.1038/s41586-024-00001-x",
    "author": [
        {"family": "Smith", "given": "J"},
        {"family": "Doe", "given": "A"},
    ],
    "issued": {"date-parts": [[2024, 1, 15]]},
    "volume": "625",
    "issue": "1",
    "page": "100-105",
}

_CSL_MULTI = [
    {
        "type": "article-journal",
        "PMID": "11111111",
        "title": "Another important paper.",
        "container-title": "Science",
        "DOI": "10.1126/science.xyz",
        "author": [{"family": "Lee", "given": "B"}],
        "issued": {"date-parts": [[2023, 3]]},
    },
    {
        "type": "article-journal",
        "PMID": "22222222",
        "title": "Cell biology advances.",
        "container-title": "Cell",
        "DOI": "10.1016/j.cell.2023.05.001",
        "author": [{"family": "Garcia", "given": "C"}],
        "issued": {"date-parts": [[2023, 6]]},
    },
]


def _make_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Tests -- core functionality
# ---------------------------------------------------------------------------


class TestCiteEmpty:
    def test_empty_input_returns_empty_list(self) -> None:
        result = cite([])
        assert result == []


class TestCiteSingle:
    def test_single_pmid_returns_csl_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A single valid PMID should return a list with one CSL-JSON object."""

        def _handler(request: httpx.Request) -> httpx.Response:
            if "ctxp" in str(request.url) or "csl" in str(request.url):
                return httpx.Response(status_code=200, json=_CSL_SINGLE)
            return httpx.Response(status_code=404)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.cite.get_http_client", lambda: client)

        result = cite(["12345678"])
        assert len(result) == 1

        obj = result[0]
        assert obj["PMID"] == "12345678"
        assert obj["title"] == "A groundbreaking study on CRISPR."
        assert obj["container-title"] == "Nature"
        assert obj["DOI"] == "10.1038/s41586-024-00001-x"
        assert isinstance(obj["author"], list)
        assert len(obj["author"]) == 2


class TestCiteMultiple:
    def test_multiple_pmids_returns_multiple_objects(self, monkeypatch: pytest.MonkeyPatch) -> None:

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, json=_CSL_MULTI)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.cite.get_http_client", lambda: client)

        result = cite(["11111111", "22222222"])
        assert len(result) == 2
        pmids = {obj["PMID"] for obj in result}
        assert pmids == {"11111111", "22222222"}


class TestCiteInvalid:
    def test_invalid_pmids_silently_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PMIDs that the API cannot resolve should be silently excluded."""

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, json=[])

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.cite.get_http_client", lambda: client)

        result = cite(["99999999"])
        assert result == []


class TestCiteBatching:
    def test_batches_requests_200_per_batch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cite() should split >200 PMIDs into multiple HTTP requests."""
        request_urls: list[str] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            request_urls.append(str(request.url))
            return httpx.Response(status_code=200, json=[])

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.cite.get_http_client", lambda: client)

        pmids = [str(i) for i in range(1, 451)]
        cite(pmids, rate_limit_delay=0)

        assert len(request_urls) == 3, f"Expected 3 batches for 450 PMIDs, got {len(request_urls)}"


# ---------------------------------------------------------------------------
# Error recovery and edge cases
# ---------------------------------------------------------------------------


class TestCiteErrorRecovery:
    def test_http_error_skips_batch_continues(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When one batch fails with HTTP error, cite() should skip it and continue."""
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(status_code=500, text="Server Error")
            return httpx.Response(status_code=200, json=_CSL_MULTI)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.cite.get_http_client", lambda: client)

        # Two batches: first will fail, second should succeed
        pmids = [str(i) for i in range(1, 401)]  # 200 + 200
        result = cite(pmids, rate_limit_delay=0)

        # Should have results from the second batch only
        assert len(result) == 2, "Should recover from first batch failure and return second batch"


class TestCiteDeduplication:
    def test_duplicate_pmids_deduplicated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Passing the same PMID twice should only fetch it once."""

        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            assert "12345678,12345678" not in url, "Should deduplicate PMIDs before sending"
            return httpx.Response(status_code=200, json=_CSL_SINGLE)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.cite.get_http_client", lambda: client)

        result = cite(["12345678", "12345678"])
        assert len(result) == 1, "Should return only one result for duplicate PMID"


class TestCiteCache:
    """cite() with pm_dir caches CSL-JSON per PMID."""

    def test_cite_with_cache_avoids_refetch(
        self, pm_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        request_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(status_code=200, json=_CSL_SINGLE)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.cite.get_http_client", lambda: client)

        # First call should fetch
        result1 = cite(["12345678"], pm_dir=pm_dir)
        assert len(result1) == 1
        assert request_count == 1

        # Second call should use cache
        result2 = cite(["12345678"], pm_dir=pm_dir)
        assert len(result2) == 1
        assert request_count == 1, "Second call should use cache"



class TestCiteAudit:
    """cite() logs to audit.jsonl when pm_dir is provided."""

    def test_logs_cite_event(self, pm_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, json=_CSL_MULTI)

        client = httpx.Client(transport=_make_transport(_handler))
        monkeypatch.setattr("pm_tools.cite.get_http_client", lambda: client)

        cite(["11111111", "22222222"], pm_dir=pm_dir)

        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "cite"
        assert event["requested"] == 2



# =============================================================================
# PMID validation at entry point
# =============================================================================


class TestCitePmidValidation:
    """cite.main() rejects non-numeric PMIDs (path traversal, PMC IDs)."""

    def test_path_traversal_rejected(self) -> None:
        """cite.main() with a path traversal PMID returns error code 1."""
        from pm_tools.cite import main

        result = main(["../../etc/passwd"])
        assert result == 1

    def test_mixed_valid_and_invalid_rejected(self) -> None:
        """A single bad PMID in a batch causes rejection."""
        from pm_tools.cite import main

        result = main(["12345678", "../../etc/passwd"])
        assert result == 1


# ---------------------------------------------------------------------------
# URL parameter encoding (v0.3.1 phase 2.2)
# ---------------------------------------------------------------------------


class TestCiteUrlEncoding:
    """_make_cite_batch() must produce safe, well-formed URLs."""

    def test_malicious_pmid_rejected(self) -> None:
        """A PMID like '123&format=bibtex' must be rejected (non-numeric)."""
        with pytest.raises(ValueError, match="Invalid PMID"):
            _make_cite_batch(["123&format=bibtex"])



