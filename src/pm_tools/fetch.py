"""pm-fetch: Fetch PubMed XML from E-utilities API."""

from __future__ import annotations

import sys
import time

import httpx

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BATCH_SIZE = 200
RATE_LIMIT_DELAY = 0.34  # ~3 requests per second


def fetch(
    pmids: list[str],
    batch_size: int = BATCH_SIZE,
    rate_limit_delay: float = RATE_LIMIT_DELAY,
    verbose: bool = False,
) -> str:
    """Fetch PubMed XML for given PMIDs.

    Args:
        pmids: List of PMID strings.
        batch_size: Number of PMIDs per API request.
        rate_limit_delay: Delay between requests in seconds.
        verbose: If True, log progress to stderr.

    Returns:
        Raw PubMed XML string.

    Raises:
        httpx.HTTPError: On network failure.
    """
    # Filter out empty strings
    pmids = [p for p in pmids if p.strip()]
    if not pmids:
        return ""

    results: list[str] = []

    for batch_num, i in enumerate(range(0, len(pmids), batch_size)):
        if batch_num > 0 and rate_limit_delay > 0:
            time.sleep(rate_limit_delay)

        batch = pmids[i : i + batch_size]
        ids_param = ",".join(batch)

        if verbose:
            print(
                f"Fetching batch {batch_num + 1} ({len(batch)} PMIDs)...",
                file=sys.stderr,
            )

        url = f"{EFETCH_URL}?db=pubmed&id={ids_param}&rettype=abstract&retmode=xml"
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        results.append(response.text)

    return "\n".join(results)


def fetch_stream(
    pmids: list[str],
    batch_size: int = BATCH_SIZE,
    rate_limit_delay: float = RATE_LIMIT_DELAY,
    verbose: bool = False,
) -> str:
    """Fetch PubMed XML, yielding results per batch."""
    return fetch(pmids, batch_size, rate_limit_delay, verbose)


HELP_TEXT = """\
pm-fetch - Fetch PubMed XML from E-utilities API

Usage: echo "12345" | pm-fetch > articles.xml
       cat pmids.txt | pm-fetch > articles.xml

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
  echo "12345" | pm-fetch > article.xml
  cat pmids.txt | pm-fetch > articles.xml
  pm-search "CRISPR" | pm-fetch | pm-parse > results.jsonl"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm-fetch."""
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
            print("hint: use 'pm-fetch --help' for usage", file=sys.stderr)
            return 2

    # Read PMIDs from stdin
    pmids: list[str] = []
    if not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line:
                pmids.append(line)

    if not pmids:
        return 0

    try:
        xml = fetch(pmids, verbose=verbose)
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
