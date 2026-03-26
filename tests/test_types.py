"""Tests for pm_tools.types — parse output conformance to TypedDict contracts.

Verifies that parse_xml() and parse_xml_stream() output conforms structurally
to the TypedDict definitions (ArticleRecord, AuthorName, AbstractSection).
"""

from __future__ import annotations

from typing import get_type_hints

from pm_tools.parse import parse_xml

# =============================================================================
# parse_xml() output conformance
# =============================================================================


class TestParseConformance:
    """parse_xml() output conforms structurally to TypedDict definitions."""

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

    def test_minimal_article_conforms(self, minimal_article_xml: str) -> None:
        """Minimal article (only pmid) is valid under total=False."""
        articles = parse_xml(minimal_article_xml)
        assert len(articles) == 1
        assert set(articles[0].keys()) == {"pmid"}
        assert articles[0]["pmid"] == "12345"

    def test_suffix_and_literal_authors_conform(self) -> None:
        """Authors with suffix or collective name conform to AuthorName."""
        from pm_tools.types import AuthorName

        valid_keys = set(get_type_hints(AuthorName).keys())
        xml = """<PubmedArticleSet><PubmedArticle>
          <MedlineCitation>
            <PMID>99999</PMID>
            <Article>
              <AuthorList>
                <Author><LastName>Smith</LastName><ForeName>John</ForeName>
                        <Suffix>Jr</Suffix></Author>
                <Author><CollectiveName>WHO Consortium</CollectiveName></Author>
              </AuthorList>
            </Article>
          </MedlineCitation>
        </PubmedArticle></PubmedArticleSet>"""
        articles = parse_xml(xml)
        authors = articles[0]["authors"]
        assert len(authors) == 2
        for author in authors:
            assert set(author.keys()) <= valid_keys
            assert "family" in author or "literal" in author

