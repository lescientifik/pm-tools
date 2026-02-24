"""Tests for pm_tools.types — TypedDict schema conformance.

Verifies that:
  - TypedDict classes are importable from pm_tools.types and pm_tools
  - Schema has the expected fields, required/optional keys
  - parse_xml() output conforms structurally to the TypedDict definitions
"""

from __future__ import annotations

from typing import get_type_hints

from pm_tools.parse import parse_xml

# =============================================================================
# Import availability
# =============================================================================


class TestTypeImports:
    """TypedDict classes importable from both pm_tools.types and pm_tools."""

    def test_import_from_types_module(self) -> None:
        from pm_tools.types import AbstractSection, ArticleRecord, AuthorName

        assert ArticleRecord is not None
        assert AuthorName is not None
        assert AbstractSection is not None

    def test_import_from_package(self) -> None:
        from pm_tools import AbstractSection, ArticleRecord, AuthorName

        assert ArticleRecord is not None
        assert AuthorName is not None
        assert AbstractSection is not None

    def test_same_class_both_paths(self) -> None:
        from pm_tools.types import ArticleRecord as ArticleRecordFromTypes

        from pm_tools import ArticleRecord

        assert ArticleRecord is ArticleRecordFromTypes


# =============================================================================
# ArticleRecord schema
# =============================================================================


class TestArticleRecordSchema:
    """ArticleRecord has 10 fields, pmid required, rest optional."""

    def test_expected_fields(self) -> None:
        from pm_tools.types import ArticleRecord

        hints = get_type_hints(ArticleRecord)
        expected = {
            "pmid",
            "title",
            "authors",
            "journal",
            "year",
            "date",
            "abstract",
            "abstract_sections",
            "doi",
            "pmcid",
        }
        assert set(hints.keys()) == expected

    def test_field_count(self) -> None:
        from pm_tools.types import ArticleRecord

        assert len(get_type_hints(ArticleRecord)) == 10

    def test_pmid_required(self) -> None:
        from pm_tools.types import ArticleRecord

        assert "pmid" in ArticleRecord.__required_keys__

    def test_optional_keys(self) -> None:
        from pm_tools.types import ArticleRecord

        expected_optional = {
            "title",
            "authors",
            "journal",
            "year",
            "date",
            "abstract",
            "abstract_sections",
            "doi",
            "pmcid",
        }
        assert ArticleRecord.__optional_keys__ == expected_optional


# =============================================================================
# AuthorName schema
# =============================================================================


class TestAuthorNameSchema:
    """AuthorName has 4 optional keys: family, given, suffix, literal."""

    def test_expected_fields(self) -> None:
        from pm_tools.types import AuthorName

        hints = get_type_hints(AuthorName)
        assert set(hints.keys()) == {"family", "given", "suffix", "literal"}

    def test_all_optional(self) -> None:
        from pm_tools.types import AuthorName

        assert AuthorName.__required_keys__ == frozenset()

    def test_optional_keys(self) -> None:
        from pm_tools.types import AuthorName

        assert AuthorName.__optional_keys__ == {"family", "given", "suffix", "literal"}


# =============================================================================
# AbstractSection schema
# =============================================================================


class TestAbstractSectionSchema:
    """AbstractSection has label + text, both required (total=True)."""

    def test_expected_fields(self) -> None:
        from pm_tools.types import AbstractSection

        hints = get_type_hints(AbstractSection)
        assert set(hints.keys()) == {"label", "text"}

    def test_both_required(self) -> None:
        from pm_tools.types import AbstractSection

        assert AbstractSection.__required_keys__ == {"label", "text"}

    def test_no_optional_keys(self) -> None:
        from pm_tools.types import AbstractSection

        assert AbstractSection.__optional_keys__ == frozenset()


# =============================================================================
# parse_xml() output conformance
# =============================================================================


class TestParseConformance:
    """parse_xml() output conforms structurally to TypedDict definitions."""

    def test_complete_article_keys_subset(self, complete_article_xml: str) -> None:
        """All keys in parsed output are valid ArticleRecord fields."""
        from pm_tools.types import ArticleRecord

        valid_keys = set(get_type_hints(ArticleRecord).keys())
        articles = parse_xml(complete_article_xml)
        assert len(articles) == 1
        assert set(articles[0].keys()) <= valid_keys

    def test_complete_article_value_types(self, complete_article_xml: str) -> None:
        """Value types match ArticleRecord annotations."""
        articles = parse_xml(complete_article_xml)
        art = articles[0]

        assert isinstance(art["pmid"], str)
        assert isinstance(art["title"], str)
        assert isinstance(art["year"], int)
        assert isinstance(art["authors"], list)
        assert isinstance(art["journal"], str)
        assert isinstance(art["doi"], str)

    def test_authors_conform_to_author_name(self, complete_article_xml: str) -> None:
        """Each author entry has only valid AuthorName keys."""
        from pm_tools.types import AuthorName

        valid_keys = set(get_type_hints(AuthorName).keys())
        articles = parse_xml(complete_article_xml)
        for author in articles[0]["authors"]:
            assert set(author.keys()) <= valid_keys
            for v in author.values():
                assert isinstance(v, str)

    def test_abstract_sections_conform(self, structured_abstract_xml: str) -> None:
        """Each abstract section has only valid AbstractSection keys."""
        from pm_tools.types import AbstractSection

        valid_keys = set(get_type_hints(AbstractSection).keys())
        articles = parse_xml(structured_abstract_xml)
        assert "abstract_sections" in articles[0]
        for section in articles[0]["abstract_sections"]:
            assert set(section.keys()) == valid_keys
            assert isinstance(section["label"], str)
            assert isinstance(section["text"], str)

    def test_union_of_fixtures_covers_all_fields(
        self, complete_article_xml: str, structured_abstract_xml: str
    ) -> None:
        """Union of keys from complete + structured fixtures covers all TypedDict fields."""
        from pm_tools.types import ArticleRecord

        all_td_keys = set(get_type_hints(ArticleRecord).keys())
        arts1 = parse_xml(complete_article_xml)
        arts2 = parse_xml(structured_abstract_xml)
        union_keys = set(arts1[0].keys()) | set(arts2[0].keys())
        assert union_keys == all_td_keys

    def test_minimal_article_conforms(self, minimal_article_xml: str) -> None:
        """Minimal article (only pmid) is valid under total=False."""
        from pm_tools.types import ArticleRecord

        valid_keys = set(get_type_hints(ArticleRecord).keys())
        articles = parse_xml(minimal_article_xml)
        assert len(articles) == 1
        assert set(articles[0].keys()) <= valid_keys
        assert articles[0]["pmid"] == "12345"
