"""pm cite: Fetch CSL-JSON citations from NCBI Citation Exporter API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from pm_tools.cache import cached_batch_fetch
from pm_tools.http import get_client as get_http_client
from pm_tools.io import safe_parse
from pm_tools.types import CslJsonRecord

API_URL = "https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/"
BATCH_SIZE = 200
RATE_LIMIT_DELAY = 0.34


def _make_cite_batch(batch_pmids: list[str]) -> list[tuple[str, str]]:
    """Fetch a batch of CSL-JSON citations from the NCBI Citation Exporter API.

    This is the ``fetch_batch`` callback for ``cached_batch_fetch()``.
    Recovers from HTTP errors by returning an empty list for failed batches.

    Args:
        batch_pmids: List of PMID strings for one batch.

    Returns:
        List of (pmid, json_string) pairs.
    """
    client = get_http_client()
    ids_param = ",".join(batch_pmids)
    url = f"{API_URL}?format=csl&id={ids_param}"

    try:
        response = client.get(url)
        response.raise_for_status()

        data = response.json()
        items = data if isinstance(data, list) else [data]
        pairs: list[tuple[str, str]] = []
        for item in items:
            pmid = item.get("PMID", "")
            if pmid:
                pairs.append((pmid, json.dumps(item, ensure_ascii=False)))
        return pairs
    except (httpx.HTTPStatusError, httpx.HTTPError):
        return []


def cite(
    pmids: list[str],
    batch_size: int = BATCH_SIZE,
    rate_limit_delay: float = RATE_LIMIT_DELAY,
    verbose: bool = False,
    *,
    pm_dir: Path | None = None,
    refresh: bool = False,
) -> list[CslJsonRecord]:
    """Fetch CSL-JSON citations for given PMIDs.

    Deduplicates PMIDs before fetching. Recovers from per-batch HTTP errors.

    Args:
        pmids: List of PMID strings.
        batch_size: Number of PMIDs per API request.
        rate_limit_delay: Delay between requests in seconds.
        verbose: If True, log progress to stderr.
        pm_dir: Path to .pm/ directory for caching and audit logging, or None.
        refresh: If True, bypass cache and re-fetch.

    Returns:
        List of CSL-JSON citation dicts.
    """
    if not pmids:
        return []

    # Deduplicate while preserving order (for result assembly below)
    seen: set[str] = set()
    unique_pmids: list[str] = []
    for pmid in pmids:
        if pmid not in seen:
            seen.add(pmid)
            unique_pmids.append(pmid)

    data = cached_batch_fetch(
        ids=unique_pmids,
        pm_dir=pm_dir,
        cache_category="cite",
        cache_ext=".json",
        fetch_batch=_make_cite_batch,
        batch_size=batch_size,
        rate_limit_delay=rate_limit_delay,
        refresh=refresh,
        verbose=verbose,
    )

    # Build result list: parse JSON strings back to dicts, in original order
    results: list[CslJsonRecord] = []
    for pmid in unique_pmids:
        if pmid in data:
            results.append(json.loads(data[pmid]))
    # Include any extra PMIDs from responses not in the input list
    for pmid, val in data.items():
        if pmid not in seen:
            results.append(json.loads(val))

    return results


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for pm cite."""
    parser = argparse.ArgumentParser(
        prog="pm cite",
        description="Fetch CSL-JSON citations from NCBI Citation Exporter API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show progress on stderr")
    parser.add_argument("pmids", nargs="*", help="PMIDs to cite (also reads from stdin)")
    return parser


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm cite."""
    if args is None:
        args = sys.argv[1:]

    parser = _build_parser()
    parsed, code = safe_parse(parser, args)
    if parsed is None:
        return code  # type: ignore[return-value]

    verbose: bool = parsed.verbose
    pmids: list[str] = parsed.pmids

    # Read from stdin if no PMIDs as arguments
    if not pmids and not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line:
                pmids.append(line)

    if not pmids:
        return 0

    # Detect .pm/ for cache + audit
    from pm_tools.cache import find_pm_dir

    detected_pm_dir = find_pm_dir()

    try:
        citations = cite(
            pmids,
            verbose=verbose,
            pm_dir=detected_pm_dir,
        )
        for citation in citations:
            print(json.dumps(citation, ensure_ascii=False))
        return 0
    except httpx.HTTPError as e:
        print(f"Error: Network request failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
