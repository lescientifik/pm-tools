"""pm fetch: Fetch PubMed XML from E-utilities API."""

from __future__ import annotations

import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from pm_tools.cache import audit_log, cache_read, cache_write

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BATCH_SIZE = 200
RATE_LIMIT_DELAY = 0.34  # ~3 requests per second

XML_HEADER = '<?xml version="1.0" ?>\n'
XML_DOCTYPE = (
    '<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN"\n'
    ' "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">\n'
)


def _merge_xml_responses(responses: list[str]) -> str:
    """Merge multiple efetch XML responses into a single valid document.

    Each response is a complete XML document with its own declaration and
    PubmedArticleSet root. This function extracts all article elements
    and wraps them in a single PubmedArticleSet.
    """
    if not responses:
        return ""

    if len(responses) == 1:
        return responses[0]

    # Collect all article elements from all responses
    fragments: list[str] = []
    for resp in responses:
        try:
            root = ET.fromstring(resp)
        except ET.ParseError:
            continue
        for child in root:
            child.tail = None
            fragments.append(ET.tostring(child, encoding="unicode"))

    if not fragments:
        return ""

    articles_xml = "\n".join(fragments)
    return f"{XML_HEADER}{XML_DOCTYPE}<PubmedArticleSet>\n{articles_xml}\n</PubmedArticleSet>"


def split_xml_articles(xml: str) -> dict[str, str]:
    """Split a PubmedArticleSet XML into per-PMID fragments.

    Args:
        xml: Full PubmedArticleSet XML document.

    Returns:
        Dict mapping PMID string to standalone XML fragment string.
        Each fragment is a single <PubmedArticle> or <PubmedBookArticle>.
    """
    if not xml or not xml.strip():
        return {}

    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}

    result: dict[str, str] = {}
    for child in root:
        pmid_elem = child.find(".//PMID")
        if pmid_elem is not None and pmid_elem.text:
            child.tail = None
            fragment = ET.tostring(child, encoding="unicode")
            result[pmid_elem.text] = fragment
    return result


def _reassemble_xml(fragments: list[str]) -> str:
    """Reassemble per-article XML fragments into a PubmedArticleSet document."""
    if not fragments:
        return ""
    articles_xml = "\n".join(fragments)
    return (
        f"{XML_HEADER}{XML_DOCTYPE}"
        f"<PubmedArticleSet>\n{articles_xml}\n</PubmedArticleSet>"
    )


def fetch(
    pmids: list[str],
    batch_size: int = BATCH_SIZE,
    rate_limit_delay: float = RATE_LIMIT_DELAY,
    verbose: bool = False,
    *,
    cache_dir: Path | None = None,
    pm_dir: Path | None = None,
    refresh: bool = False,
) -> str:
    """Fetch PubMed XML for given PMIDs.

    Args:
        pmids: List of PMID strings.
        batch_size: Number of PMIDs per API request.
        rate_limit_delay: Delay between requests in seconds.
        verbose: If True, log progress to stderr.
        cache_dir: Path to .pm/ directory for caching, or None.
        pm_dir: Path to .pm/ directory for audit logging, or None.
        refresh: If True, bypass cache and re-fetch.

    Returns:
        Raw PubMed XML string.

    Raises:
        httpx.HTTPError: On network failure.
    """
    # Filter out empty strings
    pmids = [p for p in pmids if p.strip()]
    if not pmids:
        return ""

    # Smart-batch: check cache for each PMID
    cached_fragments: dict[str, str] = {}
    uncached_pmids: list[str] = []

    if cache_dir is not None and not refresh:
        for pmid in pmids:
            cached = cache_read(cache_dir, "fetch", f"{pmid}.xml")
            if cached is not None:
                cached_fragments[pmid] = cached
            else:
                uncached_pmids.append(pmid)
    else:
        uncached_pmids = list(pmids)

    # Fetch only uncached PMIDs from API
    fetched_fragments: dict[str, str] = {}
    if uncached_pmids:
        responses: list[str] = []

        for batch_num, i in enumerate(range(0, len(uncached_pmids), batch_size)):
            if batch_num > 0 and rate_limit_delay > 0:
                time.sleep(rate_limit_delay)

            batch = uncached_pmids[i : i + batch_size]
            ids_param = ",".join(batch)

            if verbose:
                print(
                    f"Fetching batch {batch_num + 1} ({len(batch)} PMIDs)...",
                    file=sys.stderr,
                )

            url = (
                f"{EFETCH_URL}?db=pubmed&id={ids_param}"
                f"&rettype=abstract&retmode=xml"
            )
            response = httpx.get(url, timeout=30)
            response.raise_for_status()
            responses.append(response.text)

        merged = _merge_xml_responses(responses)

        # No cache: return merged XML directly (skip split/reassemble)
        if cache_dir is None and not cached_fragments:
            if pm_dir is not None:
                audit_log(
                    pm_dir,
                    {
                        "op": "fetch",
                        "db": "pubmed",
                        "requested": len(pmids),
                        "cached": 0,
                        "fetched": len(pmids),
                        "refreshed": refresh,
                    },
                )
            return merged

        # Split fetched XML into per-PMID fragments and cache them
        if merged:
            fetched_fragments = split_xml_articles(merged)
            for pmid, fragment in fetched_fragments.items():
                cache_write(cache_dir, "fetch", f"{pmid}.xml", fragment)

    # Audit log
    if pm_dir is not None:
        audit_log(
            pm_dir,
            {
                "op": "fetch",
                "db": "pubmed",
                "requested": len(pmids),
                "cached": len(cached_fragments),
                "fetched": len(fetched_fragments),
                "refreshed": refresh,
            },
        )

    # Reassemble all fragments (cached + fetched) in original order
    all_fragments: list[str] = []
    for pmid in pmids:
        if pmid in cached_fragments:
            all_fragments.append(cached_fragments[pmid])
        elif pmid in fetched_fragments:
            all_fragments.append(fetched_fragments[pmid])

    return _reassemble_xml(all_fragments)


def fetch_stream(
    pmids: list[str],
    batch_size: int = BATCH_SIZE,
    rate_limit_delay: float = RATE_LIMIT_DELAY,
    verbose: bool = False,
) -> str:
    """Fetch PubMed XML, yielding results per batch."""
    return fetch(pmids, batch_size, rate_limit_delay, verbose)


HELP_TEXT = """\
pm fetch - Fetch PubMed XML from E-utilities API

Usage: echo "12345" | pm fetch > articles.xml
       cat pmids.txt | pm fetch > articles.xml

Options:
  -v, --verbose  Show progress on stderr
  -h, --help     Show this help message

Input:
  PMIDs from stdin, one per line

Output:
  PubMed XML to stdout

Features:
  - Batches requests (200 PMIDs per API call)
  - Rate limits to ~3 requests/second
  - Exits with error on network failure

Examples:
  echo "12345" | pm fetch > article.xml
  cat pmids.txt | pm fetch > articles.xml
  pm search "CRISPR" | pm fetch | pm parse > results.jsonl"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm fetch."""
    if args is None:
        args = sys.argv[1:]

    verbose = False
    for arg in args:
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg in ("--verbose", "-v"):
            verbose = True
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            print("hint: use 'pm fetch --help' for usage", file=sys.stderr)
            return 2

    # Read PMIDs from stdin
    pmids: list[str] = []
    if not sys.stdin.isatty():
        for line in sys.stdin:
            stripped = line.strip()
            if stripped:
                pmids.append(stripped)

    if not pmids:
        return 0

    # Detect .pm/ for cache + audit
    from pm_tools.cache import find_pm_dir

    detected_pm_dir = find_pm_dir()

    try:
        xml = fetch(
            pmids,
            verbose=verbose,
            cache_dir=detected_pm_dir,
            pm_dir=detected_pm_dir,
        )
        if xml:
            print(xml, end="")
        return 0
    except httpx.HTTPError as e:
        print(f"Error: Network request failed: {e}", file=sys.stderr)
        print("hint: check your internet connection and try again", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
