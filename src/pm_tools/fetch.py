"""pm fetch: Fetch PubMed XML from E-utilities API."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from pm_tools.cache import cached_batch_fetch
from pm_tools.http import get_client

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
    return f"{XML_HEADER}{XML_DOCTYPE}<PubmedArticleSet>\n{articles_xml}\n</PubmedArticleSet>"


def _make_efetch_batch(batch_pmids: list[str]) -> list[tuple[str, str]]:
    """Fetch a batch of PMIDs from E-utilities and split into per-PMID fragments.

    This is the ``fetch_batch`` callback for ``cached_batch_fetch()``.

    Args:
        batch_pmids: List of PMID strings for one batch.

    Returns:
        List of (pmid, xml_fragment) pairs.
    """
    ids_param = ",".join(batch_pmids)
    url = f"{EFETCH_URL}?db=pubmed&id={ids_param}&rettype=abstract&retmode=xml"
    response = get_client().get(url)
    response.raise_for_status()

    fragments = split_xml_articles(response.text)
    return list(fragments.items())


def fetch(
    pmids: list[str],
    batch_size: int = BATCH_SIZE,
    rate_limit_delay: float = RATE_LIMIT_DELAY,
    verbose: bool = False,
    *,
    pm_dir: Path | None = None,
    refresh: bool = False,
) -> str:
    """Fetch PubMed XML for given PMIDs.

    Args:
        pmids: List of PMID strings.
        batch_size: Number of PMIDs per API request.
        rate_limit_delay: Delay between requests in seconds.
        verbose: If True, log progress to stderr.
        pm_dir: Path to .pm/ directory for caching and audit logging, or None.
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

    data = cached_batch_fetch(
        ids=pmids,
        pm_dir=pm_dir,
        cache_category="fetch",
        cache_ext=".xml",
        fetch_batch=_make_efetch_batch,
        batch_size=batch_size,
        rate_limit_delay=rate_limit_delay,
        refresh=refresh,
        verbose=verbose,
    )

    # Reassemble fragments in original PMID order
    fragments = [data[p] for p in pmids if p in data]
    # Include any fragments whose IDs weren't in the requested list
    seen = set(pmids)
    for p, frag in data.items():
        if p not in seen:
            fragments.append(frag)
    return _reassemble_xml(fragments)


HELP_TEXT = """\
pm fetch - Fetch PubMed XML from E-utilities API

Tip: for most tasks, use 'pm collect' instead — it runs search + fetch + parse
in one command: pm collect "query" --max 100 > results.jsonl

Usage: cat pmids.txt | pm fetch > articles.xml

Options:
  -v, --verbose  Show progress on stderr
  -h, --help     Show this help message

Input:
  PMIDs from stdin, one per line

Output:
  PubMed XML to stdout

Examples:
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
