"""pm filter: Filter JSONL articles by field patterns."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pm_tools.cache import audit_log, find_pm_dir
from pm_tools.io import read_jsonl, safe_parse


def _parse_year_filter(year_str: str) -> tuple[int | None, int | None]:
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
    if not re.match(r"^\d*-?\d*$", year_str):
        raise ValueError(f"Invalid year format '{year_str}'")

    if "-" in year_str:
        parts = year_str.split("-", 1)
        year_min = int(parts[0]) if parts[0] else None
        year_max = int(parts[1]) if parts[1] else None
        return year_min, year_max
    else:
        val = int(year_str)
        return val, val


def _matches_year(article: dict[str, Any], year_min: int | None, year_max: int | None) -> bool:
    """Check if article matches year filter."""
    year = article.get("year")
    if year is None:
        return False
    # Support both int (new) and str (legacy JSONL files)
    if isinstance(year, str):
        try:
            year = int(year)
        except ValueError:
            return False
    if year_min is not None and year < year_min:
        return False
    return not (year_max is not None and year > year_max)


def _matches_journal(article: dict[str, Any], pattern: str) -> bool:
    """Check if article journal contains pattern (case-insensitive)."""
    journal = article.get("journal", "")
    return pattern.lower() in journal.lower()


def _matches_journal_exact(article: dict[str, Any], value: str) -> bool:
    """Check if article journal matches exactly."""
    return article.get("journal") == value


def _matches_author(article: dict[str, Any], pattern: str) -> bool:
    """Check if any author contains pattern (case-insensitive).

    Searches concatenation of 'family given' or 'literal' for substring match.
    """
    authors = article.get("authors", [])
    pattern_lower = pattern.lower()
    for author in authors:
        literal = author.get("literal", "")
        if literal:
            full = literal
        else:
            full = author.get("family", "")
            given = author.get("given", "")
            if given:
                full = f"{full} {given}"
        if pattern_lower in full.lower():
            return True
    return False


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


def _build_criteria_dict(
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
) -> dict[str, Any]:
    """Build a criteria dict from filter kwargs for audit logging.

    Only includes keys whose values are truthy / not None.
    """
    criteria: dict[str, Any] = {}
    if year is not None:
        criteria["year"] = year
    if journal is not None:
        criteria["journal"] = journal
    if journal_exact is not None:
        criteria["journal_exact"] = journal_exact
    if author is not None:
        criteria["author"] = author
    if title is not None:
        criteria["title"] = title
    if pmid is not None:
        criteria["pmid"] = pmid
    if min_authors is not None:
        criteria["min_authors"] = min_authors
    if has_abstract:
        criteria["has_abstract"] = True
    if has_doi:
        criteria["has_doi"] = True
    return criteria


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


def filter_articles_audited(
    articles: Iterator[dict[str, Any]],
    *,
    pm_dir: Path | None = None,
    year: str | None = None,
    journal: str | None = None,
    journal_exact: str | None = None,
    author: str | None = None,
    title: str | None = None,
    pmid: str | None = None,
    min_authors: int | None = None,
    has_abstract: bool = False,
    has_doi: bool = False,
) -> list[dict[str, Any]]:
    """Filter articles and log PRISMA screening stats to audit trail.

    Consumes the iterator and returns a list (needed to count totals).

    Args:
        articles: Iterator of article dicts.
        pm_dir: Path to .pm/ directory for audit logging, or None.
        **kwargs: Same filter criteria as filter_articles().

    Returns:
        List of articles matching all filters.
    """
    input_list = list(articles)
    input_count = len(input_list)

    result = list(
        filter_articles(
            iter(input_list),
            year=year,
            journal=journal,
            journal_exact=journal_exact,
            author=author,
            title=title,
            pmid=pmid,
            min_authors=min_authors,
            has_abstract=has_abstract,
            has_doi=has_doi,
        )
    )
    output_count = len(result)

    if pm_dir is not None:
        criteria = _build_criteria_dict(
            year=year,
            journal=journal,
            journal_exact=journal_exact,
            author=author,
            title=title,
            pmid=pmid,
            min_authors=min_authors,
            has_abstract=has_abstract,
            has_doi=has_doi,
        )

        audit_log(
            pm_dir,
            {
                "op": "filter",
                "input": input_count,
                "output": output_count,
                "excluded": input_count - output_count,
                "criteria": criteria,
            },
        )

    return result


def filter_with_breakdown(
    articles: list[dict[str, Any]],
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
) -> tuple[list[dict[str, Any]], list[tuple[str, int]]]:
    """Apply filters one at a time and track per-step counts.

    Returns:
        Tuple of (filtered_articles, steps) where steps is a list of
        (label, count) pairs showing how many articles survive each filter.
    """
    # Build ordered list of active filters (CLI-exposed only, in application order)
    active_filters: list[tuple[str, dict[str, Any]]] = []
    if year is not None:
        active_filters.append((f"--year {year}", {"year": year}))
    if journal is not None:
        active_filters.append((f"--journal {journal}", {"journal": journal}))
    if journal_exact is not None:
        label = f"--journal-exact {journal_exact}"
        active_filters.append((label, {"journal_exact": journal_exact}))
    if author is not None:
        active_filters.append((f"--author {author}", {"author": author}))
    if title is not None:
        active_filters.append((f"--title {title}", {"title": title}))
    if pmid is not None:
        active_filters.append((f"--pmid {pmid}", {"pmid": pmid}))
    if min_authors is not None:
        active_filters.append((f"--min-authors {min_authors}", {"min_authors": min_authors}))
    if has_abstract:
        active_filters.append(("--has-abstract", {"has_abstract": True}))
    if has_doi:
        active_filters.append(("--has-doi", {"has_doi": True}))

    remaining = list(articles)
    steps: list[tuple[str, int]] = []
    for label, single_kwarg in active_filters:
        remaining = list(filter_articles(iter(remaining), **single_kwarg))
        steps.append((label, len(remaining)))

    return remaining, steps


def format_breakdown(
    input_count: int,
    steps: list[tuple[str, int]],
    output_count: int,
) -> str:
    """Format per-filter breakdown for stderr output.

    Args:
        input_count: Number of articles read.
        steps: List of (label, count) pairs from filter_with_breakdown.
        output_count: Number of articles after all filters.

    Returns:
        Formatted multi-line string for stderr.
    """
    lines = [f"{input_count} read"]
    for label, count in steps:
        lines.append(f"  → {count} after {label}")
    excluded = input_count - output_count
    lines.append(f"{output_count}/{input_count} passed ({excluded} excluded)")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    """Build argument parser for pm filter."""
    parser = argparse.ArgumentParser(
        prog="pm filter",
        description="Filter JSONL articles by field patterns.",
    )
    parser.add_argument("--year", default=None, help="Year filter (2024, 2020-2024, 2020-, -2024)")
    parser.add_argument(
        "--journal", default=None, help="Journal contains PATTERN (case-insensitive)"
    )
    parser.add_argument(
        "--journal-exact", default=None, dest="journal_exact", help="Journal equals STR exactly"
    )
    parser.add_argument(
        "--author", default=None, help="Any author contains PATTERN (case-insensitive)"
    )
    parser.add_argument(
        "--title", default=None, help="Title contains PATTERN (case-insensitive)"
    )
    parser.add_argument(
        "--pmid", default=None, help="PMID exact match (comma-separated for multiple)"
    )
    parser.add_argument(
        "--min-authors",
        default=None,
        type=int,
        dest="min_authors",
        help="Minimum number of authors",
    )
    parser.add_argument(
        "--has-abstract",
        action="store_true",
        dest="has_abstract",
        help="Article has non-empty abstract",
    )
    parser.add_argument("--has-doi", action="store_true", dest="has_doi", help="Article has DOI")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show filter stats on stderr")
    parser.add_argument(
        "--count", action="store_true", help="Print result count instead of articles"
    )
    return parser


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm filter."""
    if args is None:
        args = sys.argv[1:]

    parser = _build_parser()
    parsed, code = safe_parse(parser, args)
    if parsed is None:
        return code  # type: ignore[return-value]

    # Validate year filter format
    if parsed.year is not None:
        try:
            _parse_year_filter(parsed.year)
        except ValueError as e:
            print(f"Error: {e}. Use: 2024, 2020-2024, 2020-, or -2024", file=sys.stderr)
            return 1

    # Detect .pm/ for audit
    detected_pm_dir = find_pm_dir()

    # Process stdin
    articles = read_jsonl(sys.stdin)

    filter_kwargs: dict[str, Any] = {
        "year": parsed.year,
        "journal": parsed.journal,
        "journal_exact": parsed.journal_exact,
        "author": parsed.author,
        "title": parsed.title,
        "pmid": parsed.pmid,
        "min_authors": parsed.min_authors,
        "has_abstract": parsed.has_abstract,
        "has_doi": parsed.has_doi,
    }

    if parsed.verbose or detected_pm_dir is not None:
        # Consume into list for counting and breakdown
        input_list = list(articles)
        result, steps = filter_with_breakdown(input_list, **filter_kwargs)

        if parsed.count:
            print(len(result))
        else:
            for article in result:
                print(json.dumps(article, ensure_ascii=False))

        # Audit log (preserve existing schema)
        if detected_pm_dir is not None:
            criteria = _build_criteria_dict(**filter_kwargs)
            audit_log(
                detected_pm_dir,
                {
                    "op": "filter",
                    "input": len(input_list),
                    "output": len(result),
                    "excluded": len(input_list) - len(result),
                    "criteria": criteria,
                },
            )

        if parsed.verbose:
            print(
                format_breakdown(len(input_list), steps, len(result)),
                file=sys.stderr,
            )
    else:
        filtered = filter_articles(articles, **filter_kwargs)
        if parsed.count:
            print(sum(1 for _ in filtered))
        else:
            for article in filtered:
                print(json.dumps(article, ensure_ascii=False))

    return 0
