"""pm cite: Fetch CSL-JSON citations from NCBI Citation Exporter API."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from pm_tools.cache import audit_log, cache_read, cache_write

API_URL = "https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/"
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


def cite(
    pmids: list[str],
    batch_size: int = BATCH_SIZE,
    rate_limit_delay: float = RATE_LIMIT_DELAY,
    verbose: bool = False,
    *,
    cache_dir: Path | None = None,
    pm_dir: Path | None = None,
    refresh: bool = False,
) -> list[dict]:
    """Fetch CSL-JSON citations for given PMIDs.

    Deduplicates PMIDs before fetching. Recovers from per-batch HTTP errors.

    Args:
        pmids: List of PMID strings.
        batch_size: Number of PMIDs per API request.
        rate_limit_delay: Delay between requests in seconds.
        verbose: If True, log progress to stderr.
        cache_dir: Path to .pm/ directory for caching, or None.
        pm_dir: Path to .pm/ directory for audit logging, or None.
        refresh: If True, bypass cache and re-fetch.

    Returns:
        List of CSL-JSON citation dicts.
    """
    if not pmids:
        return []

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_pmids: list[str] = []
    for pmid in pmids:
        if pmid not in seen:
            seen.add(pmid)
            unique_pmids.append(pmid)

    # Smart-batch: check cache for each PMID
    cached_results: dict[str, dict] = {}
    uncached_pmids: list[str] = []

    if cache_dir is not None and not refresh:
        for pmid in unique_pmids:
            cached = cache_read(cache_dir, "cite", f"{pmid}.json")
            if cached is not None:
                cached_results[pmid] = json.loads(cached)
            else:
                uncached_pmids.append(pmid)
    else:
        uncached_pmids = list(unique_pmids)

    # Fetch only uncached PMIDs from API
    fetched_results: dict[str, dict] = {}
    flat_results: list[dict] = []
    client = get_http_client()

    for batch_num, i in enumerate(range(0, len(uncached_pmids), batch_size)):
        if batch_num > 0 and rate_limit_delay > 0:
            time.sleep(rate_limit_delay)

        batch = uncached_pmids[i : i + batch_size]
        ids_param = ",".join(batch)

        if verbose:
            print(
                f"Fetching batch {batch_num + 1}: {ids_param[:50]}...",
                file=sys.stderr,
            )

        url = f"{API_URL}?format=csl&id={ids_param}"

        try:
            response = client.get(url)
            response.raise_for_status()

            data = response.json()
            items = data if isinstance(data, list) else [data]
            for item in items:
                flat_results.append(item)
                pmid = item.get("PMID", "")
                if pmid:
                    fetched_results[pmid] = item
                    if cache_dir is not None:
                        cache_write(
                            cache_dir,
                            "cite",
                            f"{pmid}.json",
                            json.dumps(item, ensure_ascii=False),
                        )
        except (httpx.HTTPStatusError, httpx.HTTPError):
            if verbose:
                print(
                    f"Batch {batch_num + 1} failed, skipping...",
                    file=sys.stderr,
                )
            continue

    # Audit log
    if pm_dir is not None:
        audit_log(
            pm_dir,
            {
                "op": "cite",
                "requested": len(unique_pmids),
                "cached": len(cached_results),
                "fetched": len(fetched_results),
                "refreshed": refresh,
            },
        )

    # No cache involved: return flat list (preserves old behavior)
    if not cached_results:
        return flat_results

    # Reassemble in original order (cached + fetched)
    results: list[dict] = []
    for pmid in unique_pmids:
        if pmid in cached_results:
            results.append(cached_results[pmid])
        elif pmid in fetched_results:
            results.append(fetched_results[pmid])

    return results


def format_citation(csl_json: dict[str, Any], style: str = "apa") -> str:
    """Format a CSL-JSON citation dict into a human-readable string.

    Args:
        csl_json: CSL-JSON citation dict.
        style: Citation style ("apa" or "vancouver").

    Returns:
        Formatted citation string.
    """
    authors = csl_json.get("author", [])
    title = csl_json.get("title", "")
    container = csl_json.get("container-title", "")

    # Extract year from issued
    year = ""
    issued = csl_json.get("issued")
    if issued:
        date_parts = issued.get("date-parts", [[]])
        if date_parts and date_parts[0]:
            year = str(date_parts[0][0])

    volume = csl_json.get("volume", "")
    issue = csl_json.get("issue", "")
    pages = csl_json.get("page", "")

    if style == "vancouver":
        # Vancouver: Author1 Init, Author2 Init. Title. Journal. Year;Vol(Issue):Pages.
        author_strs = []
        for a in authors:
            family = a.get("family", "")
            given = a.get("given", "")
            initials = "".join(w[0] for w in given.split() if w) if given else ""
            author_strs.append(f"{family} {initials}")
        authors_str = ", ".join(author_strs)

        parts = [authors_str + ".", title + "."]
        if container:
            journal_part = container + "."
            if year:
                journal_part = f"{container}. {year}"
            if volume:
                journal_part += f";{volume}"
            if issue:
                journal_part += f"({issue})"
            if pages:
                journal_part += f":{pages}"
            journal_part += "."
            parts.append(journal_part)
        return " ".join(parts)

    # APA (default): Author, A. B., & Author, C. D. (Year). Title. Journal, Vol(Issue), Pages.
    author_strs = []
    for a in authors:
        family = a.get("family", "")
        given = a.get("given", "")
        initials = ". ".join(w[0] for w in given.split() if w) + "." if given else ""
        author_strs.append(f"{family}, {initials}" if initials else family)

    if len(author_strs) > 1:
        authors_str = ", ".join(author_strs[:-1]) + ", & " + author_strs[-1]
    elif author_strs:
        authors_str = author_strs[0]
    else:
        authors_str = ""

    parts = []
    if authors_str:
        parts.append(authors_str)
    if year:
        parts.append(f"({year}).")
    else:
        parts.append("(n.d.).")
    if title:
        parts.append(title + ".")
    if container:
        journal_ref = f"*{container}*"
        if volume:
            journal_ref += f", *{volume}*"
        if issue:
            journal_ref += f"({issue})"
        if pages:
            journal_ref += f", {pages}"
        journal_ref += "."
        parts.append(journal_ref)

    return " ".join(parts)


HELP_TEXT = """\
pm cite - Fetch CSL-JSON citations from NCBI Citation Exporter API

Usage: echo "12345" | pm cite > citations.jsonl
       pm cite 12345 67890 > citations.jsonl

Options:
  -v, --verbose  Show progress on stderr
  -h, --help     Show this help message

Output:
  JSONL format (one CSL-JSON object per line)"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm cite."""
    if args is None:
        args = sys.argv[1:]

    verbose = False
    pmids: list[str] = []

    for arg in args:
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg in ("--verbose", "-v"):
            verbose = True
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            return 2
        else:
            pmids.append(arg)

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
            cache_dir=detected_pm_dir,
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
