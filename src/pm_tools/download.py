"""pm download: Download full-text articles (NXML or PDF) from PubMed Central and Unpaywall."""

from __future__ import annotations

import io
import json
import logging
import sys
import tarfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

from pm_tools.cache import audit_log

logger = logging.getLogger(__name__)


@dataclass
class PmcResult:
    """Result from PMC OA lookup: URL and format (pdf or tgz)."""

    url: str
    format: Literal["pdf", "tgz"]


BATCH_SIZE = 200
RATE_LIMIT_DELAY = 0.34
MAX_PDF_MEMBER_SIZE = 200 * 1024 * 1024  # 200 MB guard against decompression bombs

# Module-level HTTP client factory (allows monkeypatching in tests)
_http_client: httpx.Client | None = None


def get_http_client() -> httpx.Client:
    """Get or create the module-level HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=30, follow_redirects=True)
    return _http_client


def convert_pmids(
    pmids: list[str],
    email: str = "user@example.com",
) -> list[dict[str, Any]]:
    """Convert PMIDs to DOI/PMCID using NCBI ID Converter API."""
    client = get_http_client()
    results: list[dict[str, Any]] = []
    for i in range(0, len(pmids), BATCH_SIZE):
        batch = pmids[i : i + BATCH_SIZE]
        ids_param = ",".join(batch)
        url = (
            f"https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
            f"?ids={ids_param}&format=json&tool=pm-download&email={email}"
        )
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
        records = data.get("records", [])
        results.extend(records)
        if i + BATCH_SIZE < len(pmids):
            time.sleep(RATE_LIMIT_DELAY)
    return results


def pmc_lookup(pmcid: str) -> PmcResult | None:
    """Query PMC OA Service for PDF or tgz URL.

    Prefers tgz over pdf when both are available (tgz contains NXML + PDF).
    Returns PmcResult with url and format, or None if no link found.
    """
    client = get_http_client()
    url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}"
    logger.debug("PMC lookup: %s", url)
    try:
        response = client.get(url)
        if response.status_code != 200:
            logger.warning("PMC lookup %s: HTTP %d", pmcid, response.status_code)
            return None
    except httpx.HTTPError as e:
        logger.warning("PMC lookup %s: %s", pmcid, e)
        return None

    if "<error" in response.text:
        logger.warning("PMC lookup %s: API error in response", pmcid)
        return None

    try:
        root = ET.fromstring(response.text)
        pdf_href: str | None = None
        tgz_href: str | None = None
        for link in root.iter("link"):
            fmt = link.get("format")
            href = link.get("href")
            if not href:
                continue
            if href.startswith("ftp://"):
                href = href.replace("ftp://", "https://", 1)
            if fmt == "pdf":
                pdf_href = href
            elif fmt == "tgz":
                tgz_href = href

        if tgz_href:
            logger.debug("PMC lookup %s: found tgz link", pmcid)
            return PmcResult(url=tgz_href, format="tgz")
        if pdf_href:
            logger.debug("PMC lookup %s: found pdf link", pmcid)
            return PmcResult(url=pdf_href, format="pdf")
    except ET.ParseError as e:
        logger.warning("PMC lookup %s: XML parse error: %s", pmcid, e)

    return None


def _extract_pdf_from_tgz(content: bytes, pmcid: str = "") -> bytes | None:
    """Extract the PDF file from a PMC tar.gz archive.

    Uses extractfile() (memory-only, no disk writes) to avoid path traversal.
    Skips members larger than MAX_PDF_MEMBER_SIZE to guard against
    decompression bombs.

    When multiple PDFs are present, prefers the one whose name contains
    the PMCID. Otherwise returns the largest PDF.

    Returns the PDF content, or None if no suitable PDF found.
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            pdf_members = [
                m
                for m in tar.getmembers()
                if m.name.lower().endswith(".pdf")
                and m.isfile()
                and 0 < m.size <= MAX_PDF_MEMBER_SIZE
            ]
            if not pdf_members:
                return None

            # Prefer member whose name contains the PMCID
            if pmcid:
                pmcid_lower = pmcid.lower()
                matching = [m for m in pdf_members if pmcid_lower in m.name.lower()]
                if matching:
                    pdf_members = matching

            # Among remaining, pick the largest (main article vs supplement)
            best = max(pdf_members, key=lambda m: m.size)
            f = tar.extractfile(best)
            if f is None:
                return None
            data = f.read()
            return data if data else None
    except (tarfile.TarError, OSError):
        return None


def _extract_nxml_from_tgz(content: bytes, pmcid: str = "") -> bytes | None:
    """Extract the NXML file from a PMC tar.gz archive.

    Uses extractfile() (memory-only, no disk writes) to avoid path traversal.
    Skips members larger than MAX_PDF_MEMBER_SIZE to guard against
    decompression bombs.

    When multiple NXML files are present, prefers the one whose name contains
    the PMCID. Otherwise returns the largest NXML.

    Returns the NXML content, or None if no suitable NXML found.
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            nxml_members = [
                m
                for m in tar.getmembers()
                if m.name.lower().endswith(".nxml")
                and m.isfile()
                and 0 < m.size <= MAX_PDF_MEMBER_SIZE
            ]
            if not nxml_members:
                return None

            # Prefer member whose name contains the PMCID
            if pmcid:
                pmcid_lower = pmcid.lower()
                matching = [m for m in nxml_members if pmcid_lower in m.name.lower()]
                if matching:
                    nxml_members = matching

            # Among remaining, pick the largest (main article vs supplement)
            best = max(nxml_members, key=lambda m: m.size)
            f = tar.extractfile(best)
            if f is None:
                return None
            data = f.read()
            return data if data else None
    except (tarfile.TarError, OSError):
        return None


def unpaywall_lookup(doi: str, email: str) -> str | None:
    """Query Unpaywall API for PDF URL."""
    client = get_http_client()
    encoded_doi = doi.replace("/", "%2F")
    url = f"https://api.unpaywall.org/v2/{encoded_doi}?email={email}"
    logger.debug("Unpaywall lookup: %s", url)
    try:
        response = client.get(url)
        if response.status_code != 200:
            logger.warning("Unpaywall lookup %s: HTTP %d", doi, response.status_code)
            return None
        data = response.json()
    except httpx.HTTPError as e:
        logger.warning("Unpaywall lookup %s: %s", doi, e)
        return None
    except json.JSONDecodeError as e:
        logger.warning("Unpaywall lookup %s: JSON decode error: %s", doi, e)
        return None

    if not data.get("is_oa"):
        logger.debug("Unpaywall lookup %s: not open access", doi)
        return None

    best_loc = data.get("best_oa_location", {})
    return best_loc.get("url_for_pdf") if best_loc else None


def find_pdf_sources(
    articles: list[dict[str, Any]],
    email: str | None = None,
    pmc_only: bool = False,
    unpaywall_only: bool = False,
) -> list[dict[str, Any]]:
    """Find PDF download sources for articles.

    Args:
        articles: List of article dicts with pmid, pmcid, doi fields.
        email: Email for Unpaywall API.
        pmc_only: Only check PMC.
        unpaywall_only: Only check Unpaywall.

    Returns:
        List of {pmid, source, url} dicts.
    """
    if not articles:
        return []

    sources: list[dict[str, Any]] = []

    for article in articles:
        pmid = article.get("pmid", "")
        pmcid = article.get("pmcid", "")
        doi = article.get("doi", "")

        try:
            # Try PMC first
            if not unpaywall_only and pmcid:
                pmc_result = pmc_lookup(pmcid)
                if pmc_result is not None:
                    sources.append(
                        {
                            "pmid": pmid,
                            "source": "pmc",
                            "url": pmc_result.url,
                            "pmcid": pmcid,
                            "pmc_format": pmc_result.format,
                        }
                    )
                    continue

            # Try Unpaywall
            if not pmc_only and doi and email:
                pdf_url = unpaywall_lookup(doi, email)
                if pdf_url:
                    sources.append(
                        {
                            "pmid": pmid,
                            "source": "unpaywall",
                            "url": pdf_url,
                            "doi": doi,
                        }
                    )
                    continue
        except Exception:
            logger.warning("PMID %s: unexpected error during source lookup", pmid, exc_info=True)

        # No source found — log the reason
        if not pmcid and not doi:
            logger.debug("PMID %s: no source found (no PMCID, no DOI)", pmid)
        elif not pmcid:
            logger.debug("PMID %s: no source found (no PMCID)", pmid)
        elif not doi:
            logger.debug("PMID %s: no source found (no DOI)", pmid)
        else:
            logger.debug("PMID %s: no source found (lookups returned None)", pmid)
        sources.append(
            {
                "pmid": pmid,
                "source": None,
                "url": None,
            }
        )

    return sources


MAX_RETRIES = 3
RETRYABLE_STATUS_CODES = {503, 429}


def _download_one(
    source: dict[str, Any],
    output_dir: Path,
    overwrite: bool,
    timeout: int,
    verify_pdf: bool,
    progress_callback: Any,
    prefer_pdf: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Download a single article. Returns (status, source_dict).

    For tgz sources, extracts NXML by default (falling back to PDF).
    With prefer_pdf=True, extracts PDF only (original behavior).
    For non-tgz sources, always downloads PDF directly.
    """
    pmid = source.get("pmid", "unknown")
    url = source.get("url")

    if not url:
        logger.warning("PMID %s: no PDF URL available", pmid)
        if progress_callback:
            progress_callback({"pmid": pmid, "status": "failed", "reason": "no_url"})
        return ("failed", source)

    # For non-tgz sources, we know the extension upfront
    is_tgz = source.get("pmc_format") == "tgz"
    if not is_tgz:
        out_file = output_dir / f"{pmid}.pdf"
        if out_file.exists() and not overwrite:
            if progress_callback:
                progress_callback({"pmid": pmid, "status": "skipped"})
            return ("skipped", source)

    try:
        client = get_http_client()
        response = None
        for attempt in range(MAX_RETRIES):
            response = client.get(url, timeout=timeout)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                break
            time.sleep(0.1 * (attempt + 1))

        if response is None or response.status_code not in (200, 226):
            status_code = response.status_code if response is not None else 0
            logger.warning("PMID %s: HTTP %d from %s", pmid, status_code, url)
            if progress_callback:
                progress_callback(
                    {
                        "pmid": pmid,
                        "status": "failed",
                        "reason": "http_error",
                        "status_code": status_code,
                        "url": url,
                    }
                )
            return ("failed", source)

        content = response.content
        if not content:
            logger.warning("PMID %s: empty response from %s", pmid, url)
            if progress_callback:
                progress_callback({"pmid": pmid, "status": "failed", "reason": "empty"})
            return ("failed", source)

        ext = ".pdf"

        # Handle tgz archives
        if is_tgz:
            pmcid = source.get("pmcid", "")
            if prefer_pdf:
                # Original behavior: extract PDF only
                logger.debug("PMID %s: extracting PDF from tgz archive", pmid)
                pdf_content = _extract_pdf_from_tgz(content, pmcid)
                if not pdf_content:
                    logger.warning(
                        "PMID %s: no PDF found in tgz archive from %s",
                        pmid,
                        url,
                    )
                    if progress_callback:
                        progress_callback(
                            {
                                "pmid": pmid,
                                "status": "failed",
                                "reason": "tgz_no_pdf",
                                "url": url,
                            }
                        )
                    return ("failed", source)
                content = pdf_content
                ext = ".pdf"
            else:
                # Default: try NXML first, fall back to PDF
                logger.debug("PMID %s: extracting NXML from tgz archive", pmid)
                nxml_content = _extract_nxml_from_tgz(content, pmcid)
                if nxml_content:
                    content = nxml_content
                    ext = ".nxml"
                else:
                    logger.debug("PMID %s: no NXML found, falling back to PDF", pmid)
                    pdf_content = _extract_pdf_from_tgz(content, pmcid)
                    if not pdf_content:
                        logger.warning(
                            "PMID %s: no NXML or PDF found in tgz archive from %s",
                            pmid,
                            url,
                        )
                        if progress_callback:
                            progress_callback(
                                {
                                    "pmid": pmid,
                                    "status": "failed",
                                    "reason": "tgz_no_pdf",
                                    "url": url,
                                }
                            )
                        return ("failed", source)
                    content = pdf_content
                    ext = ".pdf"

            # Overwrite check for tgz (extension determined after extraction)
            out_file = output_dir / f"{pmid}{ext}"
            if out_file.exists() and not overwrite:
                if progress_callback:
                    progress_callback({"pmid": pmid, "status": "skipped"})
                return ("skipped", source)

        if verify_pdf and ext == ".pdf" and not content[:5].startswith(b"%PDF-"):
            logger.warning("PMID %s: content is not a valid PDF from %s", pmid, url)
            if progress_callback:
                progress_callback({"pmid": pmid, "status": "failed", "reason": "not_pdf"})
            return ("failed", source)

        out_file.write_bytes(content)
        source["output_ext"] = ext
        if progress_callback:
            progress_callback({"pmid": pmid, "status": "downloaded"})
        return ("downloaded", source)
    except (httpx.HTTPError, OSError) as e:
        logger.warning("PMID %s: %s from %s", pmid, e, url)
        if progress_callback:
            progress_callback(
                {
                    "pmid": pmid,
                    "status": "failed",
                    "reason": "exception",
                    "url": url,
                }
            )
        return ("failed", source)


def download_pdfs(
    sources: list[dict[str, Any]],
    output_dir: Path,
    overwrite: bool = False,
    timeout: int = 30,
    progress_callback: Any = None,
    *,
    verify_pdf: bool = False,
    max_concurrent: int = 1,
    manifest: bool = False,
    pm_dir: Path | None = None,
    prefer_pdf: bool = False,
) -> dict[str, int]:
    """Download full-text articles from found sources.

    By default, extracts NXML from tgz archives (falling back to PDF).
    With prefer_pdf=True, extracts PDF only (original behavior).

    Args:
        sources: List of {pmid, source, url} dicts from find_pdf_sources.
        output_dir: Directory to save files.
        overwrite: Whether to overwrite existing files.
        timeout: Download timeout in seconds.
        progress_callback: Optional callable(event_dict) called per source.
        verify_pdf: Check that content starts with %PDF- magic bytes.
        max_concurrent: Maximum number of concurrent downloads.
        manifest: Write a manifest.jsonl file listing downloaded files.
        pm_dir: Path to .pm/ directory for audit logging, or None.
        prefer_pdf: Force PDF extraction from tgz archives.

    Returns:
        Dict with downloaded, skipped, failed counts.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {"downloaded": 0, "skipped": 0, "failed": 0}

    if not sources:
        if pm_dir is not None:
            audit_log(pm_dir, {"op": "download", **result, "total": 0})
        return result

    outcomes: list[tuple[str, dict[str, Any]]] = []

    if max_concurrent > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
            futures = [
                pool.submit(
                    _download_one,
                    s,
                    output_dir,
                    overwrite,
                    timeout,
                    verify_pdf,
                    progress_callback,
                    prefer_pdf,
                )
                for s in sources
            ]
            for f in futures:
                outcome = f.result()
                outcomes.append(outcome)
                result[outcome[0]] += 1
    else:
        for source in sources:
            outcome = _download_one(
                source, output_dir, overwrite, timeout, verify_pdf, progress_callback, prefer_pdf
            )
            outcomes.append(outcome)
            result[outcome[0]] += 1

    # Write manifest
    if manifest:
        manifest_lines: list[str] = []
        for status, src in outcomes:
            if status == "downloaded":
                pmid = src.get("pmid", "unknown")
                ext = src.get("output_ext", ".pdf")
                entry = {
                    "pmid": pmid,
                    "source": src.get("source"),
                    "path": str(output_dir / f"{pmid}{ext}"),
                }
                manifest_lines.append(json.dumps(entry))
        if manifest_lines:
            (output_dir / "manifest.jsonl").write_text("\n".join(manifest_lines) + "\n")

    # Audit log
    if pm_dir is not None:
        audit_log(
            pm_dir,
            {
                "op": "download",
                "total": len(sources),
                **result,
            },
        )

    return result


HELP_TEXT = """\
pm download - Download full-text articles from PubMed Central and Unpaywall

Usage:
  pm parse output | pm download [OPTIONS]
  pm download [OPTIONS] --input FILE

By default, downloads NXML (structured text) from PMC tgz archives.
Use --pdf to download PDF instead.

Input Options:
  --input FILE         Read PMIDs from file (one per line)

Output Options:
  --output-dir DIR     Output directory (default: current directory)
  --overwrite          Overwrite existing files
  --dry-run            Show what would be downloaded, don't download

Download Options:
  --pdf                Download PDF instead of NXML from tgz archives
  --timeout SECS       Download timeout in seconds (default: 30)
  --email EMAIL        Email for Unpaywall API (required for Unpaywall)

Source Options:
  --pmc-only           Only use PMC (skip Unpaywall)
  --unpaywall-only     Only use Unpaywall (skip PMC)

General:
  -v, --verbose        Show progress on stderr
  -h, --help           Show this help message

Exit Codes:
  0 - All requested articles downloaded successfully
  1 - Usage error or some downloads failed
  2 - No articles downloaded (no sources available)

Examples:
  pm search "CRISPR" | pm fetch | pm parse | pm download --output-dir ./articles/
  pm download --pdf --output-dir ./pdfs/        # Force PDF download
  pm parse output.jsonl | pm download --dry-run
  pm download --input pmids.txt --email user@example.com"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm download."""
    if args is None:
        args = sys.argv[1:]

    output_dir = Path(".")
    dry_run = False
    overwrite = False
    timeout = 30
    email: str | None = None
    input_file: str | None = None
    pmc_only = False
    unpaywall_only = False
    verbose = False
    prefer_pdf = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg in ("--verbose", "-v"):
            verbose = True
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--overwrite":
            overwrite = True
        elif arg == "--output-dir":
            i += 1
            output_dir = Path(args[i])
        elif arg == "--timeout":
            i += 1
            timeout = int(args[i])
        elif arg == "--email":
            i += 1
            email = args[i]
        elif arg == "--input":
            i += 1
            input_file = args[i]
        elif arg == "--pdf":
            prefer_pdf = True
        elif arg == "--pmc-only":
            pmc_only = True
        elif arg == "--unpaywall-only":
            unpaywall_only = True
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            return 1
        else:
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            return 1
        i += 1

    # Read input
    lines: list[str] = []
    if input_file:
        with open(input_file) as f:
            lines = [line.strip() for line in f if line.strip()]
    elif not sys.stdin.isatty():
        lines = [line.strip() for line in sys.stdin if line.strip()]

    if not lines:
        print("Error: No input provided. Use --help for usage.", file=sys.stderr)
        return 1

    # Detect format
    articles: list[dict[str, Any]] = []
    is_jsonl = lines[0].startswith("{")

    if is_jsonl:
        for line in lines:
            try:
                articles.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    else:
        pmids = lines
        if verbose:
            print("Converting PMIDs to get DOI/PMCID...", file=sys.stderr)
        converted = convert_pmids(pmids, email or "user@example.com")
        conv_by_pmid = {}
        for rec in converted:
            p = str(rec.get("pmid", ""))
            conv_by_pmid[p] = rec
        for pmid in pmids:
            rec = conv_by_pmid.get(pmid, {})
            articles.append(
                {
                    "pmid": pmid,
                    "pmcid": rec.get("pmcid", ""),
                    "doi": rec.get("doi", ""),
                }
            )

    sources = find_pdf_sources(articles, email, pmc_only, unpaywall_only)

    if dry_run:
        available = sum(1 for s in sources if s.get("url"))
        unavailable = len(sources) - available
        for source in sources:
            pmid = source["pmid"]
            if source.get("url"):
                print(f"PMID {pmid}: available via {source['source']}")
            else:
                print(f"PMID {pmid}: No source available")
        print(f"\nSummary: {available} available, {unavailable} not available")
        return 0 if available > 0 else 2

    # Configure logger for CLI output
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)

    # Detect .pm/ for audit
    from pm_tools.cache import find_pm_dir

    detected_pm_dir = find_pm_dir()

    # Logger handles stderr output; no progress_callback needed in CLI
    result = download_pdfs(
        sources,
        output_dir,
        overwrite,
        timeout,
        progress_callback=None,
        pm_dir=detected_pm_dir,
        prefer_pdf=prefer_pdf,
    )

    # User-facing summary — always printed (not a log message)
    print(
        f"Downloaded: {result['downloaded']}, "
        f"Skipped: {result['skipped']}, "
        f"Failed: {result['failed']}",
        file=sys.stderr,
    )

    if result["downloaded"] == 0 and result["skipped"] == 0:
        return 2
    return 0
