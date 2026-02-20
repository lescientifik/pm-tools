"""pm search: Search PubMed and return PMIDs."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import httpx

from pm_tools.cache import audit_log, cache_read, cache_write

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
DEFAULT_MAX = 10000


def _cache_key(query: str, max_results: int) -> str:
    """Compute cache key for a search query."""
    normalized = re.sub(r"\s+", " ", query.strip())
    key_data = json.dumps({"query": normalized, "max": max_results}, sort_keys=True)
    return hashlib.sha256(key_data.encode()).hexdigest() + ".json"


def search(
    query: str,
    max_results: int = DEFAULT_MAX,
    *,
    cache_dir: Path | None = None,
    pm_dir: Path | None = None,
    refresh: bool = False,
) -> list[str]:
    """Search PubMed and return list of PMIDs.

    Args:
        query: PubMed search query string.
        max_results: Maximum number of results to return.
        cache_dir: Path to .pm/ directory for caching, or None.
        pm_dir: Path to .pm/ directory for audit logging, or None.
        refresh: If True, bypass cache and re-fetch.

    Returns:
        List of PMID strings.

    Raises:
        ValueError: If query is empty.
        httpx.HTTPError: On network failure.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    # Check cache
    if cache_dir is not None and not refresh:
        key = _cache_key(query, max_results)
        cached = cache_read(cache_dir, "search", key)
        if cached is not None:
            data = json.loads(cached)
            pmids = data["pmids"]
            original_ts = data.get("timestamp", "")

            # Log cached hit to audit
            if pm_dir is not None:
                print(
                    f"pm: using cached search from {original_ts[:10]}. Use --refresh to update.",
                    file=sys.stderr,
                )
                audit_log(
                    pm_dir,
                    {
                        "op": "search",
                        "db": "pubmed",
                        "query": query,
                        "max": max_results,
                        "count": len(pmids),
                        "cached": True,
                        "original_ts": original_ts,
                    },
                )
            return pmids

    # API call
    encoded_query = urllib.parse.quote(query, safe="")
    url = f"{ESEARCH_URL}?db=pubmed&term={encoded_query}&retmax={max_results}&retmode=xml"

    response = httpx.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    pmids = [id_elem.text for id_elem in root.findall(".//Id") if id_elem.text]

    # Write audit BEFORE cache (crash-safety: audit is source of truth)
    if pm_dir is not None:
        audit_log(
            pm_dir,
            {
                "op": "search",
                "db": "pubmed",
                "query": query,
                "max": max_results,
                "count": len(pmids),
                "cached": False,
                "refreshed": refresh,
            },
        )

    # Write cache
    if cache_dir is not None:
        key = _cache_key(query, max_results)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        cache_data = json.dumps(
            {
                "query": query,
                "max_results": max_results,
                "pmids": pmids,
                "count": len(pmids),
                "timestamp": timestamp,
            },
            ensure_ascii=False,
        )
        cache_write(cache_dir, "search", key, cache_data)

    return pmids


HELP_TEXT = """\
pm search - Search PubMed and return PMIDs

Usage: pm search [OPTIONS] "search query"

Options:
  --max N        Maximum results to return (default: 10000)
  --refresh      Bypass cache and re-fetch from PubMed
  -h, --help     Show this help message

Output:
  PMIDs to stdout, one per line

Tip: for most tasks, use 'pm quick' instead — it runs search + fetch + parse
in one command and outputs JSONL directly:
  pm quick "CRISPR cancer therapy" --max 100 > results.jsonl

If you need raw PMIDs, save them to a file for reuse:
  pm search "CRISPR cancer therapy" --max 100 > pmids.txt
  cat pmids.txt | pm fetch | pm parse > results.jsonl

Query syntax:
  Uses PubMed query syntax. See:
  https://pubmed.ncbi.nlm.nih.gov/help/#search-tags"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm search."""
    if args is None:
        args = sys.argv[1:]

    max_results = DEFAULT_MAX
    query = ""
    refresh = False
    i = 0

    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg == "--refresh":
            refresh = True
        elif arg == "--max":
            i += 1
            if i >= len(args):
                print("Error: --max requires a number", file=sys.stderr)
                return 2
            try:
                max_results = int(args[i])
            except ValueError:
                print(
                    f"Error: --max requires a number, got '{args[i]}'",
                    file=sys.stderr,
                )
                return 2
        elif arg.startswith("--max="):
            try:
                max_results = int(arg.split("=", 1)[1])
            except ValueError:
                print("Error: --max requires a number", file=sys.stderr)
                return 2
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            print("hint: use 'pm search --help' for usage", file=sys.stderr)
            return 2
        else:
            query = arg
        i += 1

    if not query:
        print('Usage: pm search [--max N] "search query"', file=sys.stderr)
        return 1

    if not query.strip():
        print("Error: Query cannot be empty", file=sys.stderr)
        return 1

    # Detect .pm/ for cache + audit
    from pm_tools.cache import find_pm_dir

    detected_pm_dir = find_pm_dir()

    try:
        pmids = search(
            query,
            max_results,
            cache_dir=detected_pm_dir,
            pm_dir=detected_pm_dir,
            refresh=refresh,
        )
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
