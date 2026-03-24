"""pm parse: Parse PubMed XML to JSONL."""

from __future__ import annotations

import datetime
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from typing import IO, Any

from pm_tools.types import ArticleRecord, CslJsonRecord

# Fields emitted by default (without --csl) for backward compatibility.
LEGACY_FIELDS: frozenset[str] = frozenset({
    "pmid", "title", "authors", "journal", "year", "date",
    "abstract", "abstract_sections", "doi", "pmcid",
})


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


def parse_article(article: ET.Element) -> ArticleRecord:
    """Parse a single PubmedArticle element to an ArticleRecord dict.

    Fields are omitted (not set to ``None``) when the source XML lacks the
    corresponding element.  Only ``pmid`` is guaranteed on well-formed input.
    Returns an empty dict if the element has no MedlineCitation or no PMID;
    callers should check truthiness (``if parsed:``) before use.

    Returns:
        ArticleRecord with the following fields:

        - **pmid** (str, required): PubMed identifier.
        - **title** (str): Article title, with inline markup stripped.
        - **authors** (list[AuthorName]): CSL-JSON author objects.  Each has
          ``family``/``given``/``suffix`` for personal names, or ``literal``
          for collective names.
        - **journal** (str): Full journal title.
        - **year** (int): Publication year.
        - **date** (str): ISO 8601 date (``YYYY``, ``YYYY-MM``, or
          ``YYYY-MM-DD``).  Derived from PubDate, Season, or MedlineDate.
        - **abstract** (str): Plain-text abstract (sections joined by space).
        - **abstract_sections** (list[AbstractSection]): Labeled abstract
          sections, each with ``label`` and ``text``.  Only present when at
          least one AbstractText has a Label attribute.
        - **doi** (str): DOI, preferring ELocationID over ArticleIdList.
        - **pmcid** (str): PMC identifier (e.g. ``PMC1234567``).
    """
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

        # Authors (CSL-JSON structured dicts)
        author_list = art.find("AuthorList")
        if author_list is not None:
            authors: list[dict[str, str]] = []
            for author_elem in author_list.findall("Author"):
                lastname = _get_text(author_elem.find("LastName"))
                forename = _get_text(author_elem.find("ForeName"))
                collectivename = _get_text(author_elem.find("CollectiveName"))
                suffix = _get_text(author_elem.find("Suffix"))
                if lastname:
                    author_dict: dict[str, str] = {"family": lastname}
                    if forename:
                        author_dict["given"] = forename
                    if suffix:
                        author_dict["suffix"] = suffix
                    authors.append(author_dict)
                elif collectivename:
                    authors.append({"literal": collectivename})
            if authors:
                result["authors"] = authors

        # Journal
        journal = art.find("Journal")
        if journal is not None:
            journal_title = _get_text(journal.find("Title"))
            if journal_title:
                result["journal"] = journal_title

            # ISSN (prefer Print over Electronic)
            issn_print = ""
            issn_electronic = ""
            for issn_elem in journal.findall("ISSN"):
                issn_text = _get_text(issn_elem)
                if not issn_text:
                    continue
                issn_type = issn_elem.get("IssnType", "")
                if issn_type == "Print":
                    issn_print = issn_text
                elif issn_type == "Electronic":
                    issn_electronic = issn_text
            issn_value = issn_print or issn_electronic
            if issn_value:
                result["issn"] = issn_value

            # ISOAbbreviation
            iso_abbrev = _get_text(journal.find("ISOAbbreviation"))
            if iso_abbrev:
                result["journal_abbrev"] = iso_abbrev

            # Date fields + Volume/Issue
            journal_issue = journal.find("JournalIssue")
            if journal_issue is not None:
                # Volume and Issue
                volume = _get_text(journal_issue.find("Volume"))
                if volume:
                    result["volume"] = volume
                issue = _get_text(journal_issue.find("Issue"))
                if issue:
                    result["issue"] = issue

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

        # Pagination (page): prefer MedlinePgn, fallback to StartPage+EndPage
        pagination = art.find("Pagination")
        if pagination is not None:
            medline_pgn = _get_text(pagination.find("MedlinePgn"))
            if medline_pgn:
                result["page"] = medline_pgn
            else:
                start_page = _get_text(pagination.find("StartPage"))
                if start_page:
                    end_page = _get_text(pagination.find("EndPage"))
                    result["page"] = f"{start_page}-{end_page}" if end_page else start_page

        # ArticleDate (epub_date)
        for article_date in art.findall("ArticleDate"):
            if article_date.get("DateType") == "Electronic":
                ad_year = _get_text(article_date.find("Year"))
                if ad_year:
                    ad_month = _get_text(article_date.find("Month"))
                    ad_day = _get_text(article_date.find("Day"))
                    if ad_month and ad_day:
                        result["epub_date"] = f"{ad_year}-{ad_month}-{ad_day}"
                    elif ad_month:
                        result["epub_date"] = f"{ad_year}-{ad_month}"
                    else:
                        result["epub_date"] = ad_year
                break

        # DOI from ELocationID (canonical source, preferred)
        for eloc in art.findall("ELocationID"):
            if eloc.get("EIdType") == "doi" and eloc.get("ValidYN") != "N":
                text = _get_text(eloc)
                if text:
                    result["doi"] = text
                    break

    # MedlineJournalInfo — publisher_place (Country)
    medline_journal_info = citation.find("MedlineJournalInfo")
    if medline_journal_info is not None:
        country = _get_text(medline_journal_info.find("Country"))
        if country:
            result["publisher_place"] = country

    # PubmedData - ArticleIds + PublicationStatus
    pubmed_data = article.find("PubmedData")
    if pubmed_data is not None:
        # PublicationStatus
        pub_status = _get_text(pubmed_data.find("PublicationStatus"))
        if pub_status:
            result["pub_status"] = pub_status

        article_id_list = pubmed_data.find("ArticleIdList")
        if article_id_list is not None:
            for aid in article_id_list.findall("ArticleId"):
                id_type = aid.get("IdType", "")
                text = _get_text(aid)
                if id_type == "doi" and text and "doi" not in result:
                    result["doi"] = text
                elif id_type == "pmc" and text:
                    result["pmcid"] = text

    return result


def parse_xml(xml_input: str, verbose: bool = False) -> list[ArticleRecord]:
    """Parse PubMed XML string and return list of article dicts.

    Args:
        xml_input: PubMed XML string (PubmedArticleSet or single PubmedArticle).
        verbose: If True, log progress to stderr.

    Returns:
        List of ``ArticleRecord`` dicts.  See ``parse_article`` for the full
        field schema.
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


def parse_xml_stream(input_stream: IO[str] | IO[bytes]) -> Iterator[ArticleRecord]:
    """Parse PubMed XML from a stream, yielding article dicts.

    Args:
        input_stream: File-like object with PubMed XML.

    Yields:
        ``ArticleRecord`` dicts.  See ``parse_article`` for the full field
        schema.
    """
    # Read all content and parse
    # For large files, could use iterparse but ET.fromstring is simpler
    content = input_stream.read()
    text = content.decode("utf-8") if isinstance(content, bytes) else content

    yield from parse_xml(text)


def _date_str_to_parts(date_str: str) -> list[int]:
    """Convert ISO date string to CSL date-parts list of ints.

    '2024-03-15' → [2024, 3, 15]
    '2024-03'    → [2024, 3]
    '2024'       → [2024]

    Non-numeric segments are silently skipped.
    """
    parts = date_str.split("-")
    return [int(p) for p in parts if p and p.isdigit()]


def article_to_csl(record: ArticleRecord) -> CslJsonRecord:
    """Convert an ArticleRecord to a CSL-JSON record.

    Pure dict→dict transformation — no XML or I/O access.
    The ``accessed`` field uses today's date.
    """
    csl: dict[str, Any] = {}

    # Required / constant fields
    csl["id"] = f"pmid:{record['pmid']}"
    csl["type"] = "article-journal"
    csl["source"] = "PubMed"
    csl["PMID"] = record["pmid"]

    # accessed = today
    today = datetime.date.today()
    csl["accessed"] = {"date-parts": [[today.year, today.month, today.day]]}

    # Simple renames
    if "title" in record:
        csl["title"] = record["title"]
    if "authors" in record:
        csl["author"] = record["authors"]
    if "journal" in record:
        csl["container-title"] = record["journal"]
    if "journal_abbrev" in record:
        csl["container-title-short"] = record["journal_abbrev"]
    if "doi" in record:
        csl["DOI"] = record["doi"]
    if "pmcid" in record:
        csl["PMCID"] = record["pmcid"]
    if "issn" in record:
        csl["ISSN"] = record["issn"]
    if "publisher_place" in record:
        csl["publisher-place"] = record["publisher_place"]
    if "pub_status" in record:
        csl["status"] = record["pub_status"]

    # Pass-through fields (same key name)
    for field in ("volume", "issue", "page"):
        if field in record:
            csl[field] = record[field]

    # Date conversions
    if "date" in record:
        csl["issued"] = {"date-parts": [_date_str_to_parts(record["date"])]}
    if "epub_date" in record:
        csl["epub-date"] = {"date-parts": [_date_str_to_parts(record["epub_date"])]}

    return csl


def parse_xml_csl(xml_input: str, verbose: bool = False) -> list[CslJsonRecord]:
    """Parse PubMed XML and return CSL-JSON records.

    Convenience wrapper: ``parse_xml()`` + ``article_to_csl()`` on each record.
    """
    return [article_to_csl(a) for a in parse_xml(xml_input, verbose=verbose)]


def parse_xml_stream_csl(input_stream: IO[str] | IO[bytes]) -> Iterator[CslJsonRecord]:
    """Parse PubMed XML stream and yield CSL-JSON records.

    Convenience wrapper: ``parse_xml_stream()`` + ``article_to_csl()`` on each record.
    """
    for record in parse_xml_stream(input_stream):
        yield article_to_csl(record)


HELP_TEXT = """\
pm parse - Parse PubMed XML to JSONL

Tip: for most tasks, use 'pm collect' instead — it runs search + fetch + parse
in one command: pm collect "query" --max 100 > results.jsonl

Usage: cat articles.xml | pm parse [OPTIONS] > articles.jsonl

Options:
  --csl          Output CSL-JSON instead of ArticleRecord
  -v, --verbose  Show progress on stderr
  -h, --help     Show this help message

Output (default):
  One JSON object per line (JSONL format) with fields:
    pmid, title, authors, journal, year, date, doi, pmcid,
    abstract, abstract_sections

  Only 'pmid' is guaranteed; other fields are omitted when absent.
  'authors' are CSL-JSON objects ({family, given, suffix} or {literal}).
  'abstract_sections' is a [{label, text}] array for structured abstracts.

Output (--csl):
  CSL-JSON records (one per line). Fields include: id, type, source, PMID,
  title, author, container-title, DOI, issued, volume, issue, page, ISSN,
  container-title-short, publisher-place, status, epub-date, PMCID, accessed.
  Note: CSL-JSON output is not compatible with pm filter or pm diff.

Examples:
  cat pubmed.xml | pm parse > articles.jsonl
  cat pubmed.xml | pm parse --csl > citations.jsonl
  cat pubmed.xml | pm parse --verbose > articles.jsonl 2>progress.log"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm parse."""
    if args is None:
        args = sys.argv[1:]

    verbose = False
    csl_mode = False
    for arg in args:
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg in ("--verbose", "-v"):
            verbose = True
        elif arg == "--csl":
            csl_mode = True
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
        if csl_mode:
            output = article_to_csl(article)
        else:
            # Filter to legacy fields by default (backward compatibility)
            output = {k: v for k, v in article.items() if k in LEGACY_FIELDS}
        print(json.dumps(output, ensure_ascii=False))
        if verbose:
            pmid = article.get("pmid", "?")
            print(f"Parsed article {i}: PMID {pmid}", file=sys.stderr)

    return 0
