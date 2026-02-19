"""pm-search: Search PubMed and return PMIDs."""

from __future__ import annotations

import sys
import urllib.parse

import httpx

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
DEFAULT_MAX = 10000


def search(query: str, max_results: int = DEFAULT_MAX) -> list[str]:
    """Search PubMed and return list of PMIDs.

    Args:
        query: PubMed search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of PMID strings.

    Raises:
        ValueError: If query is empty.
        httpx.HTTPError: On network failure.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    encoded_query = urllib.parse.quote(query, safe="")
    url = f"{ESEARCH_URL}?db=pubmed&term={encoded_query}&retmax={max_results}&retmode=xml"

    response = httpx.get(url, timeout=30)
    response.raise_for_status()

    # Parse XML to extract IDs
    import xml.etree.ElementTree as ET

    root = ET.fromstring(response.text)
    pmids = [id_elem.text for id_elem in root.findall(".//Id") if id_elem.text]
    return pmids


HELP_TEXT = """\
pm-search - Search PubMed and return PMIDs

Usage: pm-search [OPTIONS] "search query"

Options:
  --max N        Maximum results to return (default: 10000)
  -h, --help     Show this help message

Output:
  PMIDs to stdout, one per line

Examples:
  pm-search "CRISPR cancer therapy"
  pm-search --max 100 "machine learning"
  pm-search "covid vaccine 2024" | pm-fetch | pm-parse > results.jsonl

Query syntax:
  Uses PubMed query syntax. See:
  https://pubmed.ncbi.nlm.nih.gov/help/#search-tags"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm-search."""
    if args is None:
        args = sys.argv[1:]

    max_results = DEFAULT_MAX
    query = ""
    i = 0

    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg == "--max":
            i += 1
            if i >= len(args):
                print("Error: --max requires a number", file=sys.stderr)
                return 2
            try:
                max_results = int(args[i])
            except ValueError:
                print(f"Error: --max requires a number, got '{args[i]}'", file=sys.stderr)
                return 2
        elif arg.startswith("--max="):
            try:
                max_results = int(arg.split("=", 1)[1])
            except ValueError:
                print("Error: --max requires a number", file=sys.stderr)
                return 2
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            print("hint: use 'pm-search --help' for usage", file=sys.stderr)
            return 2
        else:
            query = arg
        i += 1

    if not query:
        print('Usage: pm-search [--max N] "search query"', file=sys.stderr)
        return 1

    if not query.strip():
        print("Error: Query cannot be empty", file=sys.stderr)
        return 1

    try:
        pmids = search(query, max_results)
        for pmid in pmids:
            print(pmid)
        return 0
    except httpx.HTTPError as e:
        print(f"Error: Network request failed: {e}", file=sys.stderr)
        print("hint: check your internet connection and try again", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
