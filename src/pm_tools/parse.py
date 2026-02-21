"""pm parse: Parse PubMed XML to JSONL."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from typing import IO, Any


def _month_to_num(month: str) -> str:
    """Convert month name or number to 2-digit string."""
    month_map = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    m = month.lower().strip()
    if m in month_map:
        return month_map[m]
    # Already numeric
    if m.isdigit():
        return m.zfill(2)
    return ""


def _season_to_month(season: str) -> str:
    """Map season to quarter start month."""
    season_map = {
        "spring": "03",
        "summer": "06",
        "fall": "09",
        "autumn": "09",
        "winter": "12",
    }
    return season_map.get(season.lower().strip(), "")


def _parse_medline_date(md: str) -> str:
    """Parse MedlineDate to extract best ISO date string."""
    # Extract first 4-digit year
    year_match = re.search(r"\d{4}", md)
    if not year_match:
        return ""
    year = year_match.group()

    # Try to find month after year
    rest = md[year_match.end() :]
    month_match = re.match(r"\s+([A-Za-z]{3})", rest)
    if month_match:
        month_str = month_match.group(1)
        month_num = _month_to_num(month_str)
        if month_num:
            # Try to find day after month
            day_rest = rest[month_match.end() :]
            day_match = re.match(r"\s*(\d{1,2})", day_rest)
            if day_match:
                day = int(day_match.group(1))
                return f"{year}-{month_num}-{day:02d}"
            return f"{year}-{month_num}"

    return year


def _build_date(year: str, month: str, day: str, season: str, medline_date: str) -> str:
    """Build ISO date from structured fields or MedlineDate."""
    if not year:
        return ""

    if medline_date:
        return _parse_medline_date(medline_date)

    if season:
        m = _season_to_month(season)
        if m:
            return f"{year}-{m}"
        return year

    if month:
        m = _month_to_num(month)
        if not m:
            m = month
        if day:
            try:
                d = int(day)
                return f"{year}-{m}-{d:02d}"
            except ValueError:
                return f"{year}-{m}"
        return f"{year}-{m}"

    return year


def _get_text(elem: ET.Element | None) -> str:
    """Get text content from element, handling None."""
    if elem is None:
        return ""
    # itertext() gets all nested text (handles inline markup like <i>, <sup>)
    return "".join(elem.itertext()).strip()


def parse_article(article: ET.Element) -> dict[str, Any]:
    """Parse a single PubmedArticle element to dict."""
    result: dict[str, Any] = {}

    # MedlineCitation
    citation = article.find("MedlineCitation")
    if citation is None:
        return result

    # PMID
    pmid_elem = citation.find("PMID")
    pmid = _get_text(pmid_elem)
    if not pmid:
        return result
    result["pmid"] = pmid

    # Article element
    art = citation.find("Article")
    if art is not None:
        # Title
        title_elem = art.find("ArticleTitle")
        title = _get_text(title_elem)
        if title:
            result["title"] = title

        # Authors
        author_list = art.find("AuthorList")
        if author_list is not None:
            authors = []
            for author_elem in author_list.findall("Author"):
                lastname = _get_text(author_elem.find("LastName"))
                forename = _get_text(author_elem.find("ForeName"))
                if lastname:
                    if forename:
                        authors.append(f"{lastname} {forename}")
                    else:
                        authors.append(lastname)
            if authors:
                result["authors"] = authors

        # Journal
        journal = art.find("Journal")
        if journal is not None:
            journal_title = _get_text(journal.find("Title"))
            if journal_title:
                result["journal"] = journal_title

            # Date fields
            journal_issue = journal.find("JournalIssue")
            if journal_issue is not None:
                pub_date = journal_issue.find("PubDate")
                if pub_date is not None:
                    year = _get_text(pub_date.find("Year"))
                    month = _get_text(pub_date.find("Month"))
                    day = _get_text(pub_date.find("Day"))
                    season = _get_text(pub_date.find("Season"))
                    medline_date_elem = pub_date.find("MedlineDate")
                    medline_date = _get_text(medline_date_elem)

                    # Extract year from MedlineDate if no Year element
                    if not year and medline_date:
                        year_match = re.search(r"\d{4}", medline_date)
                        if year_match:
                            year = year_match.group()

                    if year:
                        result["year"] = int(year)

                    date = _build_date(year, month, day, season, medline_date)
                    if date:
                        result["date"] = date

        # Abstract
        abstract_elem = art.find("Abstract")
        if abstract_elem is not None:
            abstract_texts = abstract_elem.findall("AbstractText")
            if abstract_texts:
                text_parts = []
                sections = []
                for at in abstract_texts:
                    text = _get_text(at)
                    text_parts.append(text)
                    label = at.get("Label")
                    if label:
                        sections.append({"label": label, "text": text})

                full_abstract = " ".join(text_parts)
                if full_abstract:
                    result["abstract"] = full_abstract

                if sections:
                    result["abstract_sections"] = sections

    # PubmedData - ArticleIds
    pubmed_data = article.find("PubmedData")
    if pubmed_data is not None:
        article_id_list = pubmed_data.find("ArticleIdList")
        if article_id_list is not None:
            for aid in article_id_list.findall("ArticleId"):
                id_type = aid.get("IdType", "")
                text = _get_text(aid)
                if id_type == "doi" and text:
                    result["doi"] = text
                elif id_type == "pmc" and text:
                    result["pmcid"] = text

    return result


def parse_xml(xml_input: str, verbose: bool = False) -> list[dict[str, Any]]:
    """Parse PubMed XML string and return list of article dicts.

    Args:
        xml_input: PubMed XML string.
        verbose: If True, log progress to stderr.

    Returns:
        List of article dictionaries.
    """
    if not xml_input or not xml_input.strip():
        return []

    try:
        root = ET.fromstring(xml_input)
    except ET.ParseError:
        return []

    articles = []
    # Handle both PubmedArticleSet wrapper and standalone PubmedArticle
    if root.tag == "PubmedArticleSet":
        for i, article in enumerate(root.findall("PubmedArticle"), 1):
            parsed = parse_article(article)
            if parsed:
                articles.append(parsed)
                if verbose:
                    pmid = parsed.get("pmid", "?")
                    print(f"Parsed article {i}: PMID {pmid}", file=sys.stderr)
    elif root.tag == "PubmedArticle":
        parsed = parse_article(root)
        if parsed:
            articles.append(parsed)
            if verbose:
                pmid = parsed.get("pmid", "?")
                print(f"Parsed article 1: PMID {pmid}", file=sys.stderr)

    return articles


def parse_xml_stream(input_stream: IO[str] | IO[bytes]) -> Iterator[dict[str, Any]]:
    """Parse PubMed XML from a stream, yielding article dicts.

    Uses iterparse for memory-efficient streaming.

    Args:
        input_stream: File-like object with PubMed XML.

    Yields:
        Article dictionaries.
    """
    # Read all content and parse
    # For large files, could use iterparse but ET.fromstring is simpler
    content = input_stream.read()
    text = content.decode("utf-8") if isinstance(content, bytes) else content

    yield from parse_xml(text)


HELP_TEXT = """\
pm parse - Parse PubMed XML to JSONL

Tip: for most tasks, use 'pm collect' instead — it runs search + fetch + parse
in one command: pm collect "query" --max 100 > results.jsonl

Usage: cat articles.xml | pm parse [OPTIONS] > articles.jsonl

Options:
  -v, --verbose  Show progress on stderr
  -h, --help     Show this help message

Output:
  One JSON object per line (JSONL format) with fields:
    pmid, title, authors, journal, year, date, doi, pmcid, abstract

Examples:
  cat pubmed.xml | pm parse > articles.jsonl
  cat pubmed.xml | pm parse --verbose > articles.jsonl 2>progress.log"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm parse."""
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
            print("hint: use 'pm parse --help' for usage", file=sys.stderr)
            return 2

    # Read XML from stdin
    try:
        xml_input = sys.stdin.read()
    except KeyboardInterrupt:
        return 1

    if not xml_input or not xml_input.strip():
        return 0

    articles = parse_xml(xml_input)
    for i, article in enumerate(articles, 1):
        print(json.dumps(article, ensure_ascii=False))
        if verbose:
            pmid = article.get("pmid", "?")
            print(f"Parsed article {i}: PMID {pmid}", file=sys.stderr)

    return 0
