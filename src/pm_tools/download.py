"""pm download: Download full-text PDFs from PubMed Central and Unpaywall."""

from __future__ import annotations

import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from pm_tools.cache import audit_log

BATCH_SIZE = 200
RATE_LIMIT_DELAY = 0.34

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


def pmc_lookup(pmcid: str) -> str | None:
    """Query PMC OA Service for PDF URL."""
    client = get_http_client()
    url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}"
    try:
        response = client.get(url)
        if response.status_code != 200:
            return None
    except httpx.HTTPError:
        return None

    if "<error" in response.text:
        return None

    try:
        root = ET.fromstring(response.text)
        for link in root.iter("link"):
            if link.get("format") == "pdf":
                href = link.get("href")
                if href:
                    if href.startswith("ftp://"):
                        href = href.replace("ftp://", "https://", 1)
                    return href
    except ET.ParseError:
        pass

    return None


def unpaywall_lookup(doi: str, email: str) -> str | None:
    """Query Unpaywall API for PDF URL."""
    client = get_http_client()
    encoded_doi = doi.replace("/", "%2F")
    url = f"https://api.unpaywall.org/v2/{encoded_doi}?email={email}"
    try:
        response = client.get(url)
        if response.status_code != 200:
            return None
        data = response.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return None

    if not data.get("is_oa"):
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
                pdf_url = pmc_lookup(pmcid)
                if pdf_url:
                    sources.append(
                        {
                            "pmid": pmid,
                            "source": "pmc",
                            "url": pdf_url,
                            "pmcid": pmcid,
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
            pass

        # No source found
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


def download_pdfs(
    sources: list[dict[str, Any]],
    output_dir: Path,
    overwrite: bool = False,
    timeout: int = 30,
    progress_callback: Any = None,
    *,
    pm_dir: Path | None = None,
) -> dict[str, int]:
    """Download PDFs from found sources.

    Args:
        sources: List of {pmid, source, url} dicts from find_pdf_sources.
        output_dir: Directory to save PDFs.
        overwrite: Whether to overwrite existing files.
        timeout: Download timeout in seconds.
        progress_callback: Optional callable(event_dict) called per source.
        pm_dir: Path to .pm/ directory for audit logging, or None.

    Returns:
        Dict with downloaded, skipped, failed counts.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {"downloaded": 0, "skipped": 0, "failed": 0}

    if not sources:
        if pm_dir is not None:
            audit_log(pm_dir, {"op": "download", **result, "total": 0})
        return result

    client = get_http_client()

    for source in sources:
        pmid = source.get("pmid", "unknown")
        url = source.get("url")

        if not url:
            result["failed"] += 1
            if progress_callback:
                progress_callback({"pmid": pmid, "status": "failed", "reason": "no_url"})
            continue

        out_file = output_dir / f"{pmid}.pdf"

        if out_file.exists() and not overwrite:
            result["skipped"] += 1
            if progress_callback:
                progress_callback({"pmid": pmid, "status": "skipped"})
            continue

        try:
            response = None
            for attempt in range(MAX_RETRIES):
                response = client.get(url, timeout=timeout)
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    break
                time.sleep(0.1 * (attempt + 1))

            if response is None or response.status_code not in (200, 226):
                result["failed"] += 1
                if progress_callback:
                    progress_callback(
                        {
                            "pmid": pmid,
                            "status": "failed",
                            "reason": "http_error",
                        }
                    )
                continue

            content = response.content
            if not content:
                result["failed"] += 1
                if progress_callback:
                    progress_callback({"pmid": pmid, "status": "failed", "reason": "empty"})
                continue

            out_file.write_bytes(content)
            result["downloaded"] += 1
            if progress_callback:
                progress_callback({"pmid": pmid, "status": "downloaded"})
        except (httpx.HTTPError, OSError):
            result["failed"] += 1
            if progress_callback:
                progress_callback(
                    {
                        "pmid": pmid,
                        "status": "failed",
                        "reason": "exception",
                    }
                )

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
pm download - Download full-text PDFs from PubMed Central and Unpaywall

Usage:
  pm parse output | pm download [OPTIONS]
  pm download [OPTIONS] --input FILE

Input Options:
  --input FILE         Read PMIDs from file (one per line)

Output Options:
  --output-dir DIR     Output directory (default: current directory)
  --overwrite          Overwrite existing files
  --dry-run            Show what would be downloaded, don't download

Download Options:
  --timeout SECS       Download timeout in seconds (default: 30)
  --email EMAIL        Email for Unpaywall API (required for Unpaywall)

Source Options:
  --pmc-only           Only use PMC (skip Unpaywall)
  --unpaywall-only     Only use Unpaywall (skip PMC)

General:
  -v, --verbose        Show progress on stderr
  -h, --help           Show this help message

Exit Codes:
  0 - All requested PDFs downloaded successfully
  1 - Usage error or some PDFs failed
  2 - No PDFs downloaded (no sources available)

Examples:
  pm search "CRISPR" | pm fetch | pm parse | pm download --output-dir ./pdfs/
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
                print(f"PMID {pmid}: PDF available via {source['source']}")
            else:
                print(f"PMID {pmid}: No source available")
        print(f"\nSummary: {available} available, {unavailable} not available")
        return 0 if available > 0 else 2

    # Detect .pm/ for audit
    from pm_tools.cache import find_pm_dir

    detected_pm_dir = find_pm_dir()

    def _verbose_progress(event: dict[str, Any]) -> None:
        pmid = event.get("pmid", "?")
        status = event.get("status", "?")
        reason = event.get("reason", "")
        detail = f" ({reason})" if reason else ""
        print(f"PMID {pmid}: {status}{detail}", file=sys.stderr)

    callback = _verbose_progress if verbose else None
    result = download_pdfs(
        sources, output_dir, overwrite, timeout, progress_callback=callback, pm_dir=detected_pm_dir
    )

    total = result["downloaded"] + result["skipped"] + result["failed"]
    if verbose or total > 0:
        print(
            f"Downloaded: {result['downloaded']}, "
            f"Skipped: {result['skipped']}, "
            f"Failed: {result['failed']}",
            file=sys.stderr,
        )

    if result["downloaded"] == 0 and result["skipped"] == 0:
        return 2
    return 0
