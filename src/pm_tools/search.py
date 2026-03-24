"""pm search: Search PubMed and return PMIDs."""

from __future__ import annotations

import argparse
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
from pm_tools.http import get_client
from pm_tools.types import SearchCacheEntry

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
    pm_dir: Path | None = None,
    refresh: bool = False,
) -> list[str]:
    """Search PubMed and return list of PMIDs.

    Args:
        query: PubMed search query string.
        max_results: Maximum number of results to return.
        pm_dir: Path to .pm/ directory for caching and audit logging, or None.
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
    if pm_dir is not None and not refresh:
        key = _cache_key(query, max_results)
        cached = cache_read(pm_dir, "search", key)
        if cached is not None:
            data: SearchCacheEntry = json.loads(cached)
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

    response = get_client().get(url)
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
    if pm_dir is not None:
        key = _cache_key(query, max_results)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry: SearchCacheEntry = {
            "query": query,
            "max_results": max_results,
            "pmids": pmids,
            "count": len(pmids),
            "timestamp": timestamp,
        }
        cache_data = json.dumps(entry, ensure_ascii=False)
        cache_write(pm_dir, "search", key, cache_data)

    return pmids


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for pm search."""
    parser = argparse.ArgumentParser(
        prog="pm search",
        description="Search PubMed and return PMIDs.",
    )
    parser.add_argument(
        "--max", type=int, default=DEFAULT_MAX, dest="max_results",
        help="Maximum results (default: 10000)",
    )
    parser.add_argument("--refresh", action="store_true", help="Bypass cache and re-fetch")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show progress on stderr")
    parser.add_argument("query_words", nargs="*", help="Search query")
    return parser


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm search."""
    if args is None:
        args = sys.argv[1:]

    parser = _build_parser()
    try:
        parsed = parser.parse_args(args)
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0

    max_results: int = parsed.max_results
    refresh: bool = parsed.refresh
    query = " ".join(parsed.query_words)

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
