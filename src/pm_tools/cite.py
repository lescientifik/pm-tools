"""pm-cite: Fetch CSL-JSON citations from NCBI Citation Exporter API."""

from __future__ import annotations

import json
import sys
import time
from typing import Any

import httpx

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
) -> list[dict]:
    """Fetch CSL-JSON citations for given PMIDs.

    Deduplicates PMIDs before fetching. Recovers from per-batch HTTP errors.
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

    client = get_http_client()
    results: list[dict] = []

    for batch_num, i in enumerate(range(0, len(unique_pmids), batch_size)):
        if batch_num > 0 and rate_limit_delay > 0:
            time.sleep(rate_limit_delay)

        batch = unique_pmids[i : i + batch_size]
        ids_param = ",".join(batch)

        if verbose:
            print(f"Fetching batch {batch_num + 1}: {ids_param[:50]}...", file=sys.stderr)

        url = f"{API_URL}?format=csl&id={ids_param}"

        try:
            response = client.get(url)
            response.raise_for_status()

            data = response.json()
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)
        except (httpx.HTTPStatusError, httpx.HTTPError):
            # Skip failed batch, continue with others
            if verbose:
                print(f"Batch {batch_num + 1} failed, skipping...", file=sys.stderr)
            continue

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
pm-cite - Fetch CSL-JSON citations from NCBI Citation Exporter API

Usage: echo "12345" | pm-cite > citations.jsonl
       pm-cite 12345 67890 > citations.jsonl

Options:
  -v, --verbose  Show progress on stderr
  -h, --help     Show this help message

Output:
  JSONL format (one CSL-JSON object per line)"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm-cite."""
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

    try:
        citations = cite(pmids, verbose=verbose)
        for citation in citations:
            print(json.dumps(citation, ensure_ascii=False))
        return 0
    except httpx.HTTPError as e:
        print(f"Error: Network request failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
