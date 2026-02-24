# DO NOT add 'from __future__ import annotations' — PEP 563 breaks Required[] in TypedDict
"""TypedDict definitions for PubMed article records.

These types document the structure returned by ``parse_xml()`` and related
functions without changing runtime behavior (TypedDict is a dict at runtime).
"""

from typing import Required, TypedDict


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
