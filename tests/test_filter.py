"""Tests for pm_tools.filter — article filtering by year, journal, author, etc.

RED phase: these tests define the expected behavior for filter_articles().
Tests for core filtering are comprehensive. Tests for unimplemented features
(regex patterns, count mode, negation) will fail, driving new development.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pm_tools.filter import filter_articles, filter_articles_audited

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _article(
    *,
    pmid: str = "1",
    title: str = "A Title",
    authors: list[dict[str, str]] | None = None,
    journal: str = "Nature",
    year: int = 2024,
    doi: str | None = "10.1234/test",
    abstract: str = "Some abstract text.",
) -> dict:
    """Build a minimal article dict matching the pm parse JSONL schema."""
    art: dict = {
        "pmid": pmid,
        "title": title,
        "authors": authors
        if authors is not None
        else [{"family": "Smith", "given": "J"}, {"family": "Doe", "given": "A"}],
        "journal": journal,
        "year": year,
    }
    if doi is not None:
        art["doi"] = doi
    if abstract is not None:
        art["abstract"] = abstract
    return art


@pytest.fixture
def sample_articles() -> list[dict]:
    """A small set of articles spanning several years/journals/authors."""
    return [
        _article(
            pmid="1", year=2020, journal="Nature", authors=[{"family": "Smith", "given": "J"}]
        ),
        _article(
            pmid="2",
            year=2022,
            journal="Science",
            authors=[{"family": "Doe", "given": "A"}, {"family": "Smith", "given": "J"}],
        ),
        _article(
            pmid="3",
            year=2024,
            journal="Nature Medicine",
            authors=[{"family": "Lee", "given": "B"}],
        ),
        _article(
            pmid="4", year=2019, journal="The Lancet", authors=[{"family": "Garcia", "given": "C"}]
        ),
        _article(
            pmid="5",
            year=2024,
            journal="Nature",
            authors=[{"family": "Brown", "given": "D"}],
            abstract="",
            doi=None,
        ),
    ]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _filter(articles: list, **kwargs: Any) -> list[dict]:
    """Convenience wrapper: materialise the iterator returned by filter_articles."""
    return list(filter_articles(iter(articles), **kwargs))


# ---------------------------------------------------------------------------
# No-filter / empty input
# ---------------------------------------------------------------------------


class TestPassthrough:
    """When no filter flags are given every article passes through."""

    def test_no_filters_passes_all(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles)
        assert len(result) == len(sample_articles)
        assert [a["pmid"] for a in result] == ["1", "2", "3", "4", "5"]

    def test_empty_input_produces_empty_output(self) -> None:
        result = _filter([])
        assert result == []


# ---------------------------------------------------------------------------
# Year filter
# ---------------------------------------------------------------------------


class TestYearFilter:
    def test_exact_year(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, year="2024")
        assert [a["pmid"] for a in result] == ["3", "5"]

    def test_year_range_inclusive(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, year="2020-2024")
        pmids = [a["pmid"] for a in result]
        assert "1" in pmids  # 2020 -- lower bound
        assert "2" in pmids  # 2022
        assert "3" in pmids  # 2024 -- upper bound
        assert "4" not in pmids  # 2019 -- excluded

    def test_year_open_ended_minimum(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, year="2022-")
        pmids = [a["pmid"] for a in result]
        assert set(pmids) == {"2", "3", "5"}

    def test_year_open_ended_maximum(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, year="-2020")
        pmids = [a["pmid"] for a in result]
        assert set(pmids) == {"1", "4"}

    def test_year_missing_field_excludes_article(self) -> None:
        """An article without a 'year' key should be excluded by a year filter."""
        art = _article(pmid="99")
        del art["year"]
        result = _filter([art], year="2024")
        assert result == []

    def test_invalid_year_format_raises(self) -> None:
        with pytest.raises((ValueError, SystemExit)):
            _filter([], year="abc")


# ---------------------------------------------------------------------------
# Journal filter
# ---------------------------------------------------------------------------


class TestJournalFilter:
    def test_journal_case_insensitive_substring(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, journal="nature")
        pmids = [a["pmid"] for a in result]
        assert "1" in pmids
        assert "3" in pmids
        assert "5" in pmids

    def test_journal_no_match_returns_empty(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, journal="Cell")
        assert result == []


class TestJournalExactFilter:
    def test_journal_exact_match_only(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, journal_exact="Nature")
        pmids = [a["pmid"] for a in result]
        assert "1" in pmids
        assert "5" in pmids
        assert "3" not in pmids


# ---------------------------------------------------------------------------
# Author filter
# ---------------------------------------------------------------------------


class TestAuthorFilter:
    def test_author_case_insensitive_substring(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, author="smith")
        pmids = [a["pmid"] for a in result]
        assert "1" in pmids
        assert "2" in pmids

    def test_author_partial_match_within_name(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, author="gar")
        pmids = [a["pmid"] for a in result]
        assert "4" in pmids

    def test_author_no_match_returns_empty(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, author="Zzzzzzz")
        assert result == []

    def test_author_empty_authors_list(self) -> None:
        art = _article(pmid="99", authors=[])
        result = _filter([art], author="Smith")
        assert result == []

    def test_author_matches_family_name(self) -> None:
        articles = [_article(pmid="1", authors=[{"family": "Smith", "given": "J"}])]
        result = _filter(articles, author="smith")
        assert len(result) == 1

    def test_author_matches_given_name(self) -> None:
        articles = [_article(pmid="1", authors=[{"family": "Smith", "given": "John"}])]
        result = _filter(articles, author="john")
        assert len(result) == 1

    def test_author_matches_across_fields(self) -> None:
        """'smith john' matches concatenated 'Smith John'."""
        articles = [_article(pmid="1", authors=[{"family": "Smith", "given": "John"}])]
        result = _filter(articles, author="smith john")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# has-abstract / has-doi flags
# ---------------------------------------------------------------------------


class TestHasAbstract:
    def test_has_abstract_filters_for_presence(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, has_abstract=True)
        pmids = [a["pmid"] for a in result]
        assert "5" not in pmids
        assert len(pmids) == 4

    def test_has_abstract_empty_string_is_absent(self) -> None:
        art = _article(pmid="99", abstract="")
        result = _filter([art], has_abstract=True)
        assert result == []


class TestHasDoi:
    def test_has_doi_filters_for_presence(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, has_doi=True)
        pmids = [a["pmid"] for a in result]
        assert "5" not in pmids
        assert len(pmids) == 4

    def test_has_doi_empty_string_is_absent(self) -> None:
        """An article with doi="" should be treated as having no DOI."""
        art = _article(pmid="99")
        art["doi"] = ""
        result = _filter([art], has_doi=True)
        assert result == [], "Empty-string DOI should count as absent"


# ---------------------------------------------------------------------------
# Combined filters (AND logic)
# ---------------------------------------------------------------------------


class TestCombinedFilters:
    def test_multiple_filters_combine_with_and(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, year="2024", journal="nature")
        pmids = [a["pmid"] for a in result]
        assert set(pmids) == {"3", "5"}

    def test_combined_author_and_year(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, author="smith", year="2020-2022")
        pmids = [a["pmid"] for a in result]
        assert set(pmids) == {"1", "2"}

    def test_combined_filters_can_produce_empty(self, sample_articles: list[dict]) -> None:
        result = _filter(sample_articles, author="lee", journal="Science")
        assert result == []


# ---------------------------------------------------------------------------
# Edge cases / error handling
# ---------------------------------------------------------------------------


class TestFilterEdgeCases:
    def test_malformed_json_silently_skipped(self) -> None:
        """If the iterator yields a non-dict or broken item it should be skipped."""
        good = _article(pmid="1")
        articles: list = [good, "not-a-dict", None, 42, _article(pmid="2")]
        result = _filter(articles)
        assert len(result) == 2
        assert [a["pmid"] for a in result] == ["1", "2"]

    def test_filter_returns_iterator(self) -> None:
        """filter_articles must return an Iterator, not a list."""
        result = filter_articles(iter([_article()]))
        assert hasattr(result, "__next__"), "Expected an iterator (lazy evaluation)"

    def test_article_missing_journal_not_matched_by_journal_filter(self) -> None:
        art = _article(pmid="1")
        del art["journal"]
        result = _filter([art], journal="Nature")
        assert result == []

    def test_article_missing_authors_not_matched_by_author_filter(self) -> None:
        art = _article(pmid="1")
        del art["authors"]
        result = _filter([art], author="Smith")
        assert result == []


# ---------------------------------------------------------------------------
# Title filter
# ---------------------------------------------------------------------------


class TestTitleFilter:
    """filter_articles should support a title= keyword for substring search."""

    def test_title_case_insensitive_substring(self) -> None:
        articles = [
            _article(pmid="1", title="CRISPR gene editing"),
            _article(pmid="2", title="Machine learning in biology"),
            _article(pmid="3", title="Advanced CRISPR techniques"),
        ]
        result = _filter(articles, title="crispr")
        pmids = [a["pmid"] for a in result]
        assert set(pmids) == {"1", "3"}

    def test_title_no_match_returns_empty(self) -> None:
        articles = [_article(pmid="1", title="Some paper")]
        result = _filter(articles, title="nonexistent")
        assert result == []

    def test_title_combined_with_year(self) -> None:
        articles = [
            _article(pmid="1", title="CRISPR 2020", year=2020),
            _article(pmid="2", title="CRISPR 2024", year=2024),
            _article(pmid="3", title="Other topic", year=2024),
        ]
        result = _filter(articles, title="crispr", year="2024")
        assert len(result) == 1
        assert result[0]["pmid"] == "2"


# ---------------------------------------------------------------------------
# Count mode
# ---------------------------------------------------------------------------


class TestFilterCount:
    def test_count_only_returns_integer(self, sample_articles: list[dict]) -> None:
        from pm_tools.filter import count_matching

        result = count_matching(iter(sample_articles), year="2024")
        assert result == 2

    def test_count_with_no_matches(self) -> None:
        from pm_tools.filter import count_matching

        articles = [_article(pmid="1", year=2020)]
        result = count_matching(iter(articles), year="2024")
        assert result == 0


# ---------------------------------------------------------------------------
# PMID filter (not yet implemented)
# ---------------------------------------------------------------------------


class TestPmidFilter:
    """filter_articles should support a pmid= keyword for exact or set-based PMID matching.

    Not yet implemented -- drives adding PMID inclusion/exclusion filtering.
    """

    def test_pmid_exact_match(self) -> None:
        articles = [
            _article(pmid="12345"),
            _article(pmid="67890"),
            _article(pmid="11111"),
        ]
        result = _filter(articles, pmid="12345")
        assert len(result) == 1
        assert result[0]["pmid"] == "12345"

    def test_pmid_set_match(self) -> None:
        """Filter by a set of PMIDs (comma-separated)."""
        articles = [
            _article(pmid="12345"),
            _article(pmid="67890"),
            _article(pmid="11111"),
        ]
        result = _filter(articles, pmid="12345,11111")
        pmids = [a["pmid"] for a in result]
        assert set(pmids) == {"12345", "11111"}


# ---------------------------------------------------------------------------
# Min authors filter (not yet implemented)
# ---------------------------------------------------------------------------


class TestMinAuthorsFilter:
    """filter_articles should support min_authors= to filter by author count.

    Not yet implemented -- drives adding numeric threshold filters.
    """

    def test_min_authors_filters_by_count(self) -> None:
        articles = [
            _article(pmid="1", authors=[{"family": "Smith", "given": "J"}]),
            _article(
                pmid="2",
                authors=[{"family": "Smith", "given": "J"}, {"family": "Doe", "given": "A"}],
            ),
            _article(
                pmid="3",
                authors=[
                    {"family": "Smith", "given": "J"},
                    {"family": "Doe", "given": "A"},
                    {"family": "Lee", "given": "B"},
                ],
            ),
        ]
        result = _filter(articles, min_authors=2)
        pmids = [a["pmid"] for a in result]
        assert set(pmids) == {"2", "3"}

    def test_min_authors_with_other_filters(self) -> None:
        articles = [
            _article(pmid="1", authors=[{"family": "Smith", "given": "J"}], year=2024),
            _article(
                pmid="2",
                authors=[{"family": "Smith", "given": "J"}, {"family": "Doe", "given": "A"}],
                year=2024,
            ),
            _article(
                pmid="3",
                authors=[{"family": "Smith", "given": "J"}, {"family": "Doe", "given": "A"}],
                year=2020,
            ),
        ]
        result = _filter(articles, min_authors=2, year="2024")
        assert len(result) == 1
        assert result[0]["pmid"] == "2"


# ---------------------------------------------------------------------------
# Audit trail (PRISMA screening)
# ---------------------------------------------------------------------------


def _make_pm_dir(tmp_path: Path) -> Path:
    pm = tmp_path / ".pm"
    pm.mkdir()
    for sub in ("search", "fetch", "cite", "download"):
        (pm / "cache" / sub).mkdir(parents=True)
    (pm / "audit.jsonl").write_text("")
    return pm


class TestFilterAudit:
    """filter_articles_audited() logs screening stats for PRISMA."""

    def test_logs_filter_event(self, tmp_path: Path) -> None:
        pm_dir = _make_pm_dir(tmp_path)
        articles = [
            _article(pmid="1", year=2024),
            _article(pmid="2", year=2020),
            _article(pmid="3", year=2024),
        ]

        result = filter_articles_audited(iter(articles), pm_dir=pm_dir, year="2024")
        assert len(result) == 2

        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "filter"
        assert event["input"] == 3
        assert event["output"] == 2
        assert event["excluded"] == 1

    def test_logs_filter_criteria(self, tmp_path: Path) -> None:
        pm_dir = _make_pm_dir(tmp_path)
        articles = [_article(pmid="1", year=2024)]

        filter_articles_audited(
            iter(articles),
            pm_dir=pm_dir,
            year="2024",
            has_abstract=True,
        )

        event = json.loads((pm_dir / "audit.jsonl").read_text().strip().splitlines()[0])
        assert "year" in event["criteria"]
        assert "has_abstract" in event["criteria"]

    def test_returns_list_not_generator(self, tmp_path: Path) -> None:
        pm_dir = _make_pm_dir(tmp_path)
        articles = [_article(pmid="1")]

        result = filter_articles_audited(iter(articles), pm_dir=pm_dir)
        assert isinstance(result, list)
