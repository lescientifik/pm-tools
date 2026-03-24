# DO NOT add 'from __future__ import annotations' — PEP 563 turns annotations into strings,
# which breaks Required[] resolution: __required_keys__ becomes frozenset() at runtime.
"""TypedDict definitions for PubMed article records.

These types document the structure returned by ``parse_xml()`` and related
functions without changing runtime behavior (TypedDict is a dict at runtime).
"""

from typing import Any, Required, TypedDict


class SearchCacheEntry(TypedDict):
    """Cached result of a PubMed search query.

    Stored as JSON in ``.pm/cache/search/``.
    """

    query: str
    max_results: int
    pmids: list[str]
    count: int
    timestamp: str


class AuthorName(TypedDict, total=False):
    """CSL-JSON–style author name.

    At least one of ``family`` or ``literal`` is present in practice,
    but no key is formally required at the type level.
    """

    family: str
    given: str
    suffix: str
    literal: str


class AbstractSection(TypedDict):
    """A labeled section of a structured abstract.

    Both fields are always present when the section exists.
    """

    label: str
    text: str


class ArticleRecord(TypedDict, total=False):
    """One parsed PubMed article.

    Only ``pmid`` is guaranteed.  All other fields are omitted (not ``None``)
    when the source XML lacks the corresponding element.
    """

    # Legacy fields (emitted by default without --csl)
    pmid: Required[str]
    title: str
    authors: list[AuthorName]
    journal: str
    year: int
    date: str
    abstract: str
    abstract_sections: list[AbstractSection]
    doi: str
    pmcid: str

    # New fields (used by --csl, filtered out of default output)
    volume: str
    issue: str
    page: str
    issn: str
    journal_abbrev: str
    epub_date: str
    publisher_place: str
    pub_status: str


# Functional TypedDict form is required because CSL-JSON field names contain
# hyphens (container-title, publisher-place, etc.) which are not valid Python
# identifiers.
CslJsonRecord = TypedDict(
    "CslJsonRecord",
    {
        "id": Required[str],
        "type": Required[str],
        "source": str,
        "PMID": str,
        "PMCID": str,
        "title": str,
        "author": list[AuthorName],
        "container-title": str,
        "container-title-short": str,
        "issued": dict[str, list[list[int]]],
        "accessed": dict[str, list[list[int]]],
        "DOI": str,
        "ISSN": str,
        "volume": str,
        "issue": str,
        "page": str,
        "publisher-place": str,
        "status": str,
        "epub-date": dict[str, list[list[int]]],
    },
    total=False,
)
CslJsonRecord.__doc__ = """CSL-JSON citation record produced by ``article_to_csl()``.

Follows the CSL-JSON specification with NCBI extensions (PMID, PMCID,
epub-date, status).  All fields except ``id`` and ``type`` are optional.

Uses the functional TypedDict form because CSL-JSON field names contain
hyphens (e.g. ``container-title``, ``publisher-place``).
"""


class DownloadSource(TypedDict, total=False):
    """Source information for downloading a full-text article.

    ``pmid`` is always present.  Other fields depend on the resolved source
    (PMC, Unpaywall, or none found).
    """

    pmid: Required[str]
    source: str | None  # "pmc", "unpaywall", or None
    url: str | None
    pmcid: str
    doi: str
    pmc_format: str  # "pdf" or "tgz"


class DiffResult(TypedDict, total=False):
    """A single difference between two article sets, keyed by PMID.

    ``pmid`` and ``status`` are always present.  The remaining fields
    depend on the status value:

    - ``"added"`` / ``"removed"``: ``article`` holds the full record.
    - ``"changed"``: ``old``, ``new``, and ``changed_fields`` are present.
    """

    pmid: Required[str]
    status: Required[str]  # "added", "removed", "changed"
    article: dict[str, Any]  # for added/removed
    old: dict[str, Any]  # for changed
    new: dict[str, Any]  # for changed
    changed_fields: list[str]  # for changed


class AuditEvent(TypedDict, total=False):
    """A single event in the ``.pm/audit.jsonl`` log.

    ``ts`` and ``op`` are always present.  Other fields depend on the
    operation type (search, fetch, parse, download, etc.).
    """

    ts: Required[str]
    op: Required[str]
    db: str
    query: str
    count: int
    cached: bool | int
    requested: int
    fetched: int
    refreshed: bool
    input: int
    output: int
    excluded: int
    total: int
    downloaded: int
    skipped: int
    failed: int
    criteria: dict[str, Any]
    original_ts: str
    max: int
