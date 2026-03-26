"""Tests for pm_tools.parse — PubMed XML to JSONL parser.

Tests the parse functions at the Python module level:
  - parse_xml(xml_input: str) -> list[ArticleRecord]
  - parse_xml_stream(input_stream) -> Iterator[ArticleRecord]
  - main(args) CLI entry point
"""

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pm_tools.parse import parse_xml, parse_xml_stream

# =============================================================================
# Empty / edge-case input
# =============================================================================


class TestParseEmptyInput:
    """Empty or whitespace input should produce empty output."""

    def test_empty_string_returns_empty_list(self) -> None:
        """parse_xml("") returns []."""
        result = parse_xml("")
        assert result == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        """parse_xml("   ") returns []."""
        result = parse_xml("   ")
        assert result == []

    def test_stream_empty_input(self) -> None:
        """parse_xml_stream on empty stream yields nothing."""
        stream = io.StringIO("")
        result = list(parse_xml_stream(stream))
        assert result == []


# =============================================================================
# Complete article — all fields
# =============================================================================


class TestParseCompleteArticle:
    """Complete article with all standard fields."""

    def test_extracts_all_fields(self, complete_article_xml: str) -> None:
        """All standard fields are extracted from a complete article."""
        result = parse_xml(complete_article_xml)

        assert len(result) == 1
        article = result[0]

        assert article["pmid"] == "12345678"
        assert article["title"] == "Test Article Title"
        assert article["journal"] == "Nature Medicine"
        assert article["year"] == 2024
        assert article["doi"] == "10.1234/test"
        assert article["abstract"] == "This is the abstract."
        assert article["date"] == "2024-03-15"
        assert article["pmcid"] == "PMC1234567"
        assert isinstance(article["authors"], list)
        assert len(article["authors"]) == 2


# =============================================================================
# DOI source (ELocationID vs ArticleIdList)
# =============================================================================


class TestParseDOISource:
    """DOI should be extracted from ELocationID first, falling back to ArticleIdList."""

    def test_doi_from_elocationid_preferred(self) -> None:
        """When DOI exists in both ELocationID and ArticleIdList, ELocationID wins."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>100</PMID>
    <Article>
      <ArticleTitle>Test</ArticleTitle>
      <ELocationID EIdType="doi" ValidYN="Y">10.1234/elocationid-doi</ELocationID>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList>
      <ArticleId IdType="doi">10.1234/articleidlist-doi</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        assert result[0]["doi"] == "10.1234/elocationid-doi"

    def test_doi_fallback_to_articleidlist(self) -> None:
        """When DOI only exists in ArticleIdList, it is still extracted."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>101</PMID>
    <Article>
      <ArticleTitle>Test</ArticleTitle>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList>
      <ArticleId IdType="doi">10.1234/fallback-doi</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        assert result[0]["doi"] == "10.1234/fallback-doi"

    def test_doi_from_elocationid_only(self) -> None:
        """When DOI only exists in ELocationID (no DOI in ArticleIdList), it is extracted."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>102</PMID>
    <Article>
      <ArticleTitle>Test</ArticleTitle>
      <ELocationID EIdType="doi" ValidYN="Y">10.1234/eloc-only</ELocationID>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList>
      <ArticleId IdType="pubmed">102</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        assert result[0]["doi"] == "10.1234/eloc-only"

    def test_elocationid_invalid_validyn_ignored(self) -> None:
        """ELocationID with ValidYN='N' is ignored, falls back to ArticleIdList."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>103</PMID>
    <Article>
      <ArticleTitle>Test</ArticleTitle>
      <ELocationID EIdType="doi" ValidYN="N">10.1234/invalid-doi</ELocationID>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList>
      <ArticleId IdType="doi">10.1234/valid-fallback</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        assert result[0]["doi"] == "10.1234/valid-fallback"


# =============================================================================
# Authors formatting
# =============================================================================


class TestParseAuthors:
    """Author names as structured CSL-JSON dicts."""

    def test_authors_formatted_as_dicts(self) -> None:
        """Authors are structured dicts with family/given keys."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>123</PMID>
    <Article>
      <AuthorList>
        <Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
        <Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author>
      </AuthorList>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        authors = result[0]["authors"]

        assert authors[0] == {"family": "Smith", "given": "John"}
        assert authors[1] == {"family": "Doe", "given": "Jane"}
        assert set(authors[0].keys()) == {"family", "given"}

    def test_author_with_only_lastname(self) -> None:
        """Author with only LastName has no 'given' key."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>5141</PMID>
    <Article>
      <AuthorList>
        <Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
        <Author><LastName>OgataK</LastName></Author>
      </AuthorList>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        authors = result[0]["authors"]

        assert len(authors) == 2
        assert authors[0] == {"family": "Smith", "given": "John"}
        assert authors[1] == {"family": "OgataK"}
        assert "given" not in authors[1]

    def test_collective_name_as_literal(self) -> None:
        """CollectiveName authors stored as {'literal': ...}."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>201</PMID>
    <Article>
      <AuthorList>
        <Author><LastName>Smith</LastName><ForeName>J</ForeName></Author>
        <Author><CollectiveName>WHO Working Group</CollectiveName></Author>
      </AuthorList>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        authors = result[0]["authors"]

        assert len(authors) == 2
        assert authors[0] == {"family": "Smith", "given": "J"}
        assert authors[1] == {"literal": "WHO Working Group"}

    def test_author_with_suffix(self) -> None:
        """Author with Suffix element gets 'suffix' key."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>202</PMID>
    <Article>
      <AuthorList>
        <Author><LastName>Smith</LastName><ForeName>John</ForeName><Suffix>Jr</Suffix></Author>
      </AuthorList>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        authors = result[0]["authors"]

        assert authors[0] == {"family": "Smith", "given": "John", "suffix": "Jr"}


# =============================================================================
# Structured abstract
# =============================================================================


class TestParseStructuredAbstract:
    """Structured abstracts with labeled sections."""

    def test_flat_abstract_text(self, structured_abstract_xml: str) -> None:
        """The abstract field contains flat concatenated text."""
        result = parse_xml(structured_abstract_xml)
        article = result[0]

        expected = "This is background. These are methods. These are results."
        assert article["abstract"] == expected

    def test_abstract_sections_present(self, structured_abstract_xml: str) -> None:
        """abstract_sections field contains labeled sections."""
        result = parse_xml(structured_abstract_xml)
        article = result[0]

        sections = article["abstract_sections"]
        assert len(sections) == 3
        assert sections[0]["label"] == "BACKGROUND"
        assert sections[0]["text"] == "This is background."
        assert sections[1]["label"] == "METHODS"
        assert sections[1]["text"] == "These are methods."
        assert sections[2]["label"] == "RESULTS"
        assert sections[2]["text"] == "These are results."

    def test_plain_abstract_has_no_sections(self, plain_abstract_xml: str) -> None:
        """Plain abstract (no labels) should NOT have abstract_sections."""
        result = parse_xml(plain_abstract_xml)
        article = result[0]

        assert article["abstract"] == "This is a plain abstract without sections."
        assert "abstract_sections" not in article


# =============================================================================
# Multiple articles
# =============================================================================


class TestParseMultipleArticles:
    """Multiple PubmedArticles in one set."""

    def test_two_articles_produce_two_results(self, two_articles_xml: str) -> None:
        """Two articles produce a list of length 2."""
        result = parse_xml(two_articles_xml)

        assert len(result) == 2

    def test_each_article_has_correct_pmid(self, two_articles_xml: str) -> None:
        """Each article has the correct PMID."""
        result = parse_xml(two_articles_xml)

        assert result[0]["pmid"] == "111"
        assert result[1]["pmid"] == "222"

    def test_stream_yields_two_articles(self, two_articles_xml: str) -> None:
        """parse_xml_stream yields 2 dicts for 2 articles."""
        stream = io.StringIO(two_articles_xml)
        result = list(parse_xml_stream(stream))

        assert len(result) == 2
        assert result[0]["pmid"] == "111"
        assert result[1]["pmid"] == "222"


# =============================================================================
# Unicode and special characters
# =============================================================================


class TestParseUnicode:
    """Unicode characters in titles, authors, abstracts."""

    def test_unicode_in_title(self) -> None:
        """French accented characters are preserved in title."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>456</PMID>
    <Article>
      <ArticleTitle>\u00c9tude fran\u00e7aise: na\u00efve r\u00e9sum\u00e9</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["title"] == "\u00c9tude fran\u00e7aise: na\u00efve r\u00e9sum\u00e9"

    def test_unicode_in_author_names(self) -> None:
        """German umlauts are preserved in author names."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>456</PMID>
    <Article>
      <AuthorList>
        <Author><LastName>M\u00fcller</LastName><ForeName>Fran\u00e7ois</ForeName></Author>
      </AuthorList>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["authors"][0] == {"family": "M\u00fcller", "given": "Fran\u00e7ois"}


# =============================================================================
# XML entities
# =============================================================================


class TestParseXMLEntities:
    """XML entities (&amp;, &lt;, etc.) should be decoded."""

    def test_ampersand_entity(self) -> None:
        """&amp; is decoded to &."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>789</PMID>
    <Article>
      <ArticleTitle>Effects of A &amp; B on C &lt; D</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["title"] == "Effects of A & B on C < D"


# =============================================================================
# Missing optional fields
# =============================================================================


class TestParseMissingFields:
    """Articles without optional fields should not cause errors."""

    def test_missing_doi_and_abstract(self) -> None:
        """Article without DOI or abstract still parses correctly."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>999</PMID>
    <Article>
      <ArticleTitle>Title Only</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["pmid"] == "999"
        assert result[0]["title"] == "Title Only"
        # Should be valid JSON (not raise)
        json.dumps(result[0])

    def test_missing_authors(self) -> None:
        """Article without authors list is handled gracefully."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>888</PMID>
    <Article>
      <ArticleTitle>No Authors Article</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["pmid"] == "888"
        # authors should be empty list or absent, not an error
        authors = result[0].get("authors", [])
        assert isinstance(authors, list)
        assert authors == []


# =============================================================================
# Quotes and backslashes in content
# =============================================================================


class TestParseSpecialCharsInContent:
    """Quotes and backslashes must be properly JSON-escaped."""

    def test_quotes_in_title(self) -> None:
        """Double quotes in title are preserved and JSON-safe."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99903</PMID>
    <Article>
      <ArticleTitle>Study of "quoted text" and C:\\path\\to\\file in literature.</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        title = result[0]["title"]

        assert '"quoted text"' in title
        assert "C:\\path\\to\\file" in title

        # Must be JSON-serializable
        json_str = json.dumps(result[0])
        parsed_back = json.loads(json_str)
        assert parsed_back["title"] == title

    def test_backslashes_in_abstract(self) -> None:
        """Backslashes in abstract text are preserved."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99904</PMID>
    <Article>
      <Abstract>
        <AbstractText>The path C:\\data\\results\\output was used. Backslash: \\.</AbstractText>
      </Abstract>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)
        abstract = result[0]["abstract"]

        assert "C:\\data\\results\\output" in abstract

        # Must be JSON-serializable
        json_str = json.dumps(result[0])
        parsed_back = json.loads(json_str)
        assert parsed_back["abstract"] == abstract


# =============================================================================
# PMCID extraction
# =============================================================================


class TestParsePMCID:
    """PMCID from ArticleIdList."""

    def test_pmcid_extracted_when_present(self) -> None:
        """PMCID (IdType="pmc") is extracted."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345678</PMID>
    <Article>
      <ArticleTitle>Test Article</ArticleTitle>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList>
      <ArticleId IdType="pubmed">12345678</ArticleId>
      <ArticleId IdType="pmc">PMC1234567</ArticleId>
      <ArticleId IdType="doi">10.1234/test</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["pmcid"] == "PMC1234567"

    def test_pmcid_absent_when_not_present(self) -> None:
        """When no PMC ArticleId exists, pmcid key is absent from output."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345678</PMID>
    <Article>
      <ArticleTitle>Test Article</ArticleTitle>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList>
      <ArticleId IdType="pubmed">12345678</ArticleId>
      <ArticleId IdType="doi">10.1234/test</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert "pmcid" not in result[0]


# =============================================================================
# Verbose mode (stderr output)
# =============================================================================


class TestParseVerbose:
    """--verbose flag outputs progress to stderr."""

    def test_verbose_outputs_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """With verbose=True, progress info is written to stderr."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345</PMID>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        # parse_xml should accept verbose parameter
        parse_xml(xml, verbose=True)

        captured = capsys.readouterr()
        # stderr should contain the exact progress message from parse_xml
        assert "Parsed article 1: PMID 12345" in captured.err

    def test_no_verbose_stderr_is_silent(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Without verbose, stderr should be empty."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345</PMID>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        parse_xml(xml, verbose=False)

        captured = capsys.readouterr()
        assert captured.err == ""


# =============================================================================
# Date parsing
# =============================================================================


class TestParseDates:
    """Date extraction from various PubDate formats."""

    def test_full_date_iso_format(self) -> None:
        """Year+Month+Day produces YYYY-MM-DD."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99999</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <Year>1975</Year>
            <Month>Oct</Month>
            <Day>27</Day>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-10-27"
        assert result[0]["year"] == 1975

    def test_year_month_format(self) -> None:
        """Year+Month (no day) produces YYYY-MM."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99998</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <Year>1975</Year>
            <Month>Jun</Month>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-06"
        assert result[0]["year"] == 1975

    def test_year_only_format(self) -> None:
        """Year only produces YYYY."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99997</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <Year>1976</Year>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1976"
        assert result[0]["year"] == 1976

    def test_year_season_maps_to_month(self) -> None:
        """Year+Season (Summer) maps to quarter start month (06)."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99996</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <Year>1975</Year>
            <Season>Summer</Season>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-06"
        assert result[0]["year"] == 1975

    def test_numeric_month_format(self) -> None:
        """Numeric month (09) is handled correctly."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99990</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <Year>1975</Year>
            <Month>09</Month>
            <Day>15</Day>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-09-15"


# =============================================================================
# MedlineDate patterns
# =============================================================================


class TestParseMedlineDates:
    """MedlineDate is a free-text date field used when structured dates are not available."""

    def test_medlinedate_month_range(self) -> None:
        """MedlineDate "1975 Jul-Aug" extracts start month -> 1975-07."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99995</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <MedlineDate>1975 Jul-Aug</MedlineDate>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-07"
        assert result[0]["year"] == 1975

    def test_medlinedate_day_range(self) -> None:
        """MedlineDate "1977 Jul 4-7" extracts start date -> 1977-07-04."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99994</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <MedlineDate>1977 Jul 4-7</MedlineDate>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1977-07-04"
        assert result[0]["year"] == 1977

    def test_medlinedate_year_range(self) -> None:
        """MedlineDate "1975-1976" extracts start year -> 1975."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99993</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <MedlineDate>1975-1976</MedlineDate>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1975"
        assert result[0]["year"] == 1975

    def test_medlinedate_cross_year(self) -> None:
        """MedlineDate "1975 Dec-1976 Jan" extracts start month -> 1975-12."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99992</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <MedlineDate>1975 Dec-1976 Jan</MedlineDate>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-12"
        assert result[0]["year"] == 1975

    def test_medlinedate_uppercase_months(self) -> None:
        """MedlineDate "1975 MAR-APR" handles uppercase months -> 1975-03."""
        xml = """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99991</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <MedlineDate>1975 MAR-APR</MedlineDate>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-03"
        assert result[0]["year"] == 1975


# =============================================================================
# Real fixture files
# =============================================================================


class TestParseRealFixtures:
    """Tests against actual fixture XML files."""

    def test_structured_abstract_fixture(self, edge_cases_dir: Path) -> None:
        """Parse the structured-abstract fixture (PMID 541)."""
        xml_path = edge_cases_dir / "structured-abstract" / "pmid-541.xml"
        if not xml_path.exists():
            pytest.skip("Fixture not found")

        xml = xml_path.read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert len(result) == 1
        article = result[0]
        assert article["pmid"] == "541"
        assert "abstract" in article
        assert "abstract_sections" in article
        assert len(article["abstract_sections"]) == 2
        assert article["authors"] == [
            {"family": "Hummerich", "given": "W"},
            {"family": "Krause", "given": "D K"},
        ]

    def test_quotes_backslash_fixture(self, edge_cases_dir: Path) -> None:
        """Parse the quotes-backslash fixture."""
        xml_path = edge_cases_dir / "special-chars" / "quotes-backslash.xml"
        if not xml_path.exists():
            pytest.skip("Fixture not found")

        xml = xml_path.read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert len(result) == 1
        article = result[0]
        assert article["pmid"] == "99903"
        assert '"quoted text"' in article["title"]
        assert "C:\\path\\to\\file" in article["title"]

        # Output must be valid JSON
        json_str = json.dumps(article)
        json.loads(json_str)

    def test_random_fixture_pmid_11586(self, fixtures_dir: Path) -> None:
        """Parse a random fixture file and verify it produces valid JSONL."""
        xml_path = fixtures_dir / "random" / "pmid-11586.xml"
        if not xml_path.exists():
            pytest.skip("Fixture not found")

        xml = xml_path.read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert len(result) == 1
        assert result[0]["pmid"] == "11586"
        assert "title" in result[0], "Parsed article should have a title"
        # Must be JSON-serializable
        json.dumps(result[0])


class TestParseNonNumericYear:
    """Guard int(year) against non-numeric values (v0.3.1 phase 1.1)."""

    def _make_xml(self, year_content: str) -> str:
        """Build minimal PubMed XML with a given <Year> content."""
        return f"""<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>11111</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <Year>{year_content}</Year>
          </PubDate>
        </JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""

    @pytest.mark.parametrize(
        "year_content",
        ["not-a-year", "2024a", ""],
        ids=["alphabetic", "alphanumeric", "empty"],
    )
    def test_non_numeric_year_no_crash(self, year_content: str) -> None:
        """Non-numeric <Year> must not crash and must leave year field absent."""
        article = parse_xml(self._make_xml(year_content))[0]
        assert "year" not in article


# =============================================================================
# CLI: parse.main() (Phase 1.2 — streaming wiring)
# =============================================================================


# Two-article XML fixture for CLI-level tests.
_TWO_ARTICLE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>111</PMID>
    <Article>
      <ArticleTitle>First Title</ArticleTitle>
      <Journal>
        <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue>
        <Title>J One</Title>
      </Journal>
      <Abstract><AbstractText>Abstract one.</AbstractText></Abstract>
      <ELocationID EIdType="doi" ValidYN="Y">10.1/a</ELocationID>
    </Article>
  </MedlineCitation>
</PubmedArticle>
<PubmedArticle>
  <MedlineCitation>
    <PMID>222</PMID>
    <Article>
      <ArticleTitle>Second Title</ArticleTitle>
      <Journal>
        <JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue>
        <Title>J Two</Title>
      </Journal>
      <Abstract><AbstractText>Abstract two.</AbstractText></Abstract>
      <ELocationID EIdType="doi" ValidYN="Y">10.2/b</ELocationID>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>
"""


def _make_stdin_mock(xml_text: str) -> io.StringIO:
    """Create a StringIO stdin mock that also exposes a .buffer attribute."""
    mock_stdin = io.StringIO(xml_text)
    mock_stdin.buffer = io.BytesIO(xml_text.encode("utf-8"))  # type: ignore[attr-defined]
    return mock_stdin


class TestParseMainCLI:
    """CLI-level regression tests for parse.main()."""

    def test_multi_article_jsonl_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Piping multi-article XML via stdin produces 2 JSONL lines."""
        from pm_tools.parse import main

        with patch("sys.stdin", _make_stdin_mock(_TWO_ARTICLE_XML)):
            rc = main([])

        assert rc == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["pmid"] == "111"
        assert second["pmid"] == "222"
        # Legacy fields only (no issn, volume, etc.)
        assert "title" in first
        assert "abstract" in first

    def test_csl_flag_outputs_csl_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--csl flag produces CSL-JSON records with expected keys."""
        from pm_tools.parse import main

        with patch("sys.stdin", _make_stdin_mock(_TWO_ARTICLE_XML)):
            rc = main(["--csl"])

        assert rc == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 2
        csl = json.loads(lines[0])
        assert csl["type"] == "article-journal"
        assert csl["PMID"] == "111"
        assert "container-title" in csl



# =============================================================================
# format_article helper
# =============================================================================


class TestFormatArticle:
    """format_article(article, csl=False) selects output mode."""

    _ARTICLE: dict[str, object] = {
        "pmid": "12345",
        "title": "Test Article",
        "authors": [{"family": "Doe", "given": "Jane"}],
        "journal": "Test Journal",
        "year": 2024,
        "date": "2024-03",
        "abstract": "An abstract.",
        "doi": "10.1234/test",
        "pmcid": "PMC999",
        # Extra fields present in full ArticleRecord but NOT in LEGACY_FIELDS
        "issn": "1234-5678",
        "volume": "10",
        "issue": "2",
        "page": "100-110",
        "journal_abbrev": "Test J.",
        "publisher_place": "United States",
        "pub_status": "ppublish",
        "epub_date": "2024-02-15",
    }

    def test_legacy_mode_keeps_only_legacy_fields(self) -> None:
        """csl=False returns only LEGACY_FIELDS keys."""
        from pm_tools.parse import LEGACY_FIELDS, format_article

        result = format_article(self._ARTICLE)
        assert set(result.keys()) <= LEGACY_FIELDS
        # Core fields preserved
        assert result["pmid"] == "12345"
        assert result["title"] == "Test Article"
        assert result["doi"] == "10.1234/test"
        # Extra fields stripped
        assert "issn" not in result
        assert "volume" not in result
        assert "publisher_place" not in result

    def test_csl_mode_returns_csl_json(self) -> None:
        """csl=True returns a CSL-JSON record via article_to_csl."""
        from pm_tools.parse import format_article

        result = format_article(self._ARTICLE, csl=True)
        assert result["type"] == "article-journal"
        assert result["PMID"] == "12345"
        assert result["DOI"] == "10.1234/test"
        assert "container-title" in result


# =============================================================================
# TTY detection — stdin is a terminal
# =============================================================================


class TestParseTTYDetection:
    """When stdin is a TTY (no pipe), pm parse should print usage and exit 1."""

    def test_tty_stdin_prints_usage_and_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """main([]) with TTY stdin prints usage hint to stderr, returns 1."""
        from pm_tools.parse import main

        with patch("pm_tools.parse.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = main([])

        assert result == 1
        err = capsys.readouterr().err
        assert "Usage:" in err
        assert "pm parse" in err

    def test_tty_stdin_with_flags_still_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """main(["--csl"]) with TTY stdin still shows usage hint and exits 1."""
        from pm_tools.parse import main

        with patch("pm_tools.parse.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = main(["--csl"])

        assert result == 1
        err = capsys.readouterr().err
        assert "Usage:" in err

    def test_piped_stdin_works_normally(self, capsys: pytest.CaptureFixture[str]) -> None:
        """main([]) with piped stdin (isatty False) and valid XML works."""
        from pm_tools.parse import main

        xml = (
            '<PubmedArticleSet>'
            '<PubmedArticle><MedlineCitation><PMID>999</PMID>'
            '<Article><ArticleTitle>T</ArticleTitle><Journal>'
            '<Title>J</Title><ISOAbbreviation>J</ISOAbbreviation>'
            '</Journal></Article></MedlineCitation></PubmedArticle>'
            '</PubmedArticleSet>'
        )
        buf = io.BytesIO(xml.encode())

        with patch("pm_tools.parse.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer = buf
            result = main([])

        assert result == 0
        out = capsys.readouterr().out
        record = json.loads(out.strip())
        assert record["pmid"] == "999"
