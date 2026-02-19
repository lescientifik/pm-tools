"""pm filter: Filter JSONL articles by field patterns."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from typing import Any


def _parse_year_filter(year_str: str) -> tuple[str | None, str | None]:
    """Parse year filter string into (min, max) tuple.

    Supports: "2024", "2020-2024", "2020-", "-2024"

    Raises:
        ValueError: On invalid format.
    """
    if not year_str or year_str == "-":
        raise ValueError(f"Invalid year format '{year_str}'")

    # Must contain at least one digit
    if not any(c.isdigit() for c in year_str):
        raise ValueError(f"Invalid year format '{year_str}'")

    # Must only contain digits and at most one dash
    import re

    if not re.match(r"^\d*-?\d*$", year_str):
        raise ValueError(f"Invalid year format '{year_str}'")

    if "-" in year_str:
        parts = year_str.split("-", 1)
        year_min = parts[0] if parts[0] else None
        year_max = parts[1] if parts[1] else None
        return year_min, year_max
    else:
        return year_str, year_str


def _matches_year(article: dict[str, Any], year_min: str | None, year_max: str | None) -> bool:
    """Check if article matches year filter."""
    year = article.get("year")
    if year is None:
        return False
    if year_min and year < year_min:
        return False
    return not (year_max and year > year_max)


def _matches_journal(article: dict[str, Any], pattern: str) -> bool:
    """Check if article journal contains pattern (case-insensitive)."""
    journal = article.get("journal", "")
    return pattern.lower() in journal.lower()


def _matches_journal_exact(article: dict[str, Any], value: str) -> bool:
    """Check if article journal matches exactly."""
    return article.get("journal") == value


def _matches_author(article: dict[str, Any], pattern: str) -> bool:
    """Check if any author contains pattern (case-insensitive)."""
    authors = article.get("authors", [])
    pattern_lower = pattern.lower()
    return any(pattern_lower in author.lower() for author in authors)


def _has_abstract(article: dict[str, Any]) -> bool:
    """Check if article has non-empty abstract."""
    abstract = article.get("abstract")
    return abstract is not None and abstract != ""


def _has_doi(article: dict[str, Any]) -> bool:
    """Check if article has non-empty DOI."""
    doi = article.get("doi")
    return doi is not None and doi != ""


def _matches_title(article: dict[str, Any], pattern: str) -> bool:
    """Check if article title contains pattern (case-insensitive)."""
    title = article.get("title", "")
    return pattern.lower() in title.lower()


def filter_articles(
    articles: Iterator[dict[str, Any]],
    *,
    year: str | None = None,
    journal: str | None = None,
    journal_exact: str | None = None,
    author: str | None = None,
    title: str | None = None,
    pmid: str | None = None,
    min_authors: int | None = None,
    has_abstract: bool = False,
    has_doi: bool = False,
) -> Iterator[dict[str, Any]]:
    """Filter articles based on criteria.

    All filters combine with AND logic.

    Args:
        articles: Iterator of article dicts.
        year: Year filter (exact, range, or open-ended).
        journal: Journal substring filter (case-insensitive).
        journal_exact: Journal exact match filter.
        author: Author substring filter (case-insensitive).
        title: Title substring filter (case-insensitive).
        pmid: PMID filter (exact or comma-separated set).
        min_authors: Minimum number of authors required.
        has_abstract: Require non-empty abstract.
        has_doi: Require DOI.

    Yields:
        Articles matching all filters.
    """
    year_min = year_max = None
    if year is not None:
        year_min, year_max = _parse_year_filter(year)

    # Parse PMID filter (exact or comma-separated set)
    pmid_set: set[str] | None = None
    if pmid is not None:
        pmid_set = {p.strip() for p in pmid.split(",")}

    for article in articles:
        if not isinstance(article, dict):
            continue
        if pmid_set is not None and article.get("pmid") not in pmid_set:
            continue
        if year is not None and not _matches_year(article, year_min, year_max):
            continue
        if journal is not None and not _matches_journal(article, journal):
            continue
        if journal_exact is not None and not _matches_journal_exact(article, journal_exact):
            continue
        if author is not None and not _matches_author(article, author):
            continue
        if title is not None and not _matches_title(article, title):
            continue
        if min_authors is not None and len(article.get("authors", [])) < min_authors:
            continue
        if has_abstract and not _has_abstract(article):
            continue
        if has_doi and not _has_doi(article):
            continue
        yield article


def count_matching(
    articles: Iterator[dict[str, Any]],
    **kwargs: Any,
) -> int:
    """Count articles matching filter criteria.

    Accepts same kwargs as filter_articles.
    """
    return sum(1 for _ in filter_articles(articles, **kwargs))


def parse_jsonl_stream(input_stream) -> Iterator[dict[str, Any]]:
    """Parse JSONL lines from a stream, skipping malformed lines."""
    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


HELP_TEXT = """\
pm filter - Filter JSONL articles by field patterns

Usage: pm parse | pm filter [OPTIONS]
       cat articles.jsonl | pm filter [OPTIONS]

Filter Options:
  --year PATTERN      Year filter (exact, range, or open-ended)
                      Examples: 2024, 2020-2024, 2020-, -2024
  --journal PATTERN   Journal contains PATTERN (case-insensitive)
  --journal-exact STR Journal equals STR exactly
  --author PATTERN    Any author contains PATTERN (case-insensitive)
  --has-abstract      Article has non-empty abstract
  --has-doi           Article has DOI

General Options:
  -v, --verbose       Show filter stats on stderr
  -h, --help          Show this help

Examples:
  pm filter --year 2020- --journal nature --has-abstract
  pm filter --author smith
  pm filter --year 2020-2024

Notes:
  - Multiple filters combine with AND logic
  - Malformed JSON lines are silently skipped"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm filter."""
    if args is None:
        args = sys.argv[1:]

    # Parse arguments
    year_filter = None
    journal_filter = None
    journal_exact_filter = None
    author_filter = None
    want_abstract = False
    want_doi = False
    verbose = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg in ("--verbose", "-v"):
            verbose = True
        elif arg == "--year":
            i += 1
            if i >= len(args):
                print("Error: --year requires a pattern", file=sys.stderr)
                return 1
            year_filter = args[i]
        elif arg.startswith("--year="):
            year_filter = arg.split("=", 1)[1]
        elif arg == "--journal":
            i += 1
            if i >= len(args):
                print("Error: --journal requires a pattern", file=sys.stderr)
                return 1
            journal_filter = args[i]
        elif arg.startswith("--journal="):
            journal_filter = arg.split("=", 1)[1]
        elif arg == "--journal-exact":
            i += 1
            if i >= len(args):
                print("Error: --journal-exact requires a value", file=sys.stderr)
                return 1
            journal_exact_filter = args[i]
        elif arg.startswith("--journal-exact="):
            journal_exact_filter = arg.split("=", 1)[1]
        elif arg == "--author":
            i += 1
            if i >= len(args):
                print("Error: --author requires a pattern", file=sys.stderr)
                return 1
            author_filter = args[i]
        elif arg.startswith("--author="):
            author_filter = arg.split("=", 1)[1]
        elif arg == "--has-abstract":
            want_abstract = True
        elif arg == "--has-doi":
            want_doi = True
        elif arg.startswith("-"):
            print(f"Unknown option: {arg}. Use --help for usage.", file=sys.stderr)
            return 1
        else:
            print(f"Unknown option: {arg}. Use --help for usage.", file=sys.stderr)
            return 1
        i += 1

    # Validate year filter format
    if year_filter is not None:
        try:
            _parse_year_filter(year_filter)
        except ValueError as e:
            print(f"Error: {e}. Use: 2024, 2020-2024, 2020-, or -2024", file=sys.stderr)
            return 1

    # Process stdin
    articles = parse_jsonl_stream(sys.stdin)

    if verbose:
        # Count input/output
        input_count = 0
        output_count = 0
        input_list = list(articles)
        input_count = len(input_list)

        filtered = filter_articles(
            iter(input_list),
            year=year_filter,
            journal=journal_filter,
            journal_exact=journal_exact_filter,
            author=author_filter,
            has_abstract=want_abstract,
            has_doi=want_doi,
        )
        for article in filtered:
            print(json.dumps(article, ensure_ascii=False))
            output_count += 1

        print(f"{output_count}/{input_count} articles passed filters", file=sys.stderr)
    else:
        filtered = filter_articles(
            articles,
            year=year_filter,
            journal=journal_filter,
            journal_exact=journal_exact_filter,
            author=author_filter,
            has_abstract=want_abstract,
            has_doi=want_doi,
        )
        for article in filtered:
            print(json.dumps(article, ensure_ascii=False))

    return 0
