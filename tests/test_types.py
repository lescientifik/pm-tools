"""Tests for pm_tools.types — parse output conformance to TypedDict contracts.

Verifies that parse_xml() and parse_xml_stream() output conforms structurally
to the TypedDict definitions (ArticleRecord, AuthorName, AbstractSection).
"""

from __future__ import annotations

from typing import get_type_hints

from pm_tools.parse import parse_xml, parse_xml_stream

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
        assert isinstance(art["date"], str)
        assert isinstance(art["authors"], list)
        assert isinstance(art["journal"], str)
        assert isinstance(art["abstract"], str)
        assert isinstance(art["doi"], str)
        assert isinstance(art["pmcid"], str)

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

    def test_stream_output_conforms(self, complete_article_xml: str) -> None:
        """parse_xml_stream() output also conforms to ArticleRecord."""
        import io

        from pm_tools.types import ArticleRecord

        valid_keys = set(get_type_hints(ArticleRecord).keys())
        stream = io.StringIO(complete_article_xml)
        count = 0
        for article in parse_xml_stream(stream):
            assert set(article.keys()) <= valid_keys
            assert isinstance(article["pmid"], str)
            count += 1
        assert count >= 1, "parse_xml_stream should yield at least 1 article"
