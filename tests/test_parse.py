"""Tests for pm_tools.parse — PubMed XML to JSONL parser.

Tests the parse functions at the Python module level:
  - parse_xml(xml_input: str) -> list[dict]
  - parse_xml_stream(input_stream) -> Iterator[dict]

All tests are written RED-first: they MUST fail until the module is implemented.
"""

import io
import json
from pathlib import Path

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
# Minimal article — PMID extraction
# =============================================================================


class TestParseMinimalArticle:
    """Minimal XML with only PMID should be parseable."""

    def test_extracts_pmid(self, minimal_article_xml: str) -> None:
        """PMID is extracted from minimal article."""
        result = parse_xml(minimal_article_xml)

        assert len(result) == 1
        assert result[0]["pmid"] == "12345"

    def test_output_is_valid_json(self, minimal_article_xml: str) -> None:
        """Each result dict is JSON-serializable."""
        result = parse_xml(minimal_article_xml)

        for article in result:
            # Should not raise
            json_str = json.dumps(article)
            # And should round-trip
            parsed_back = json.loads(json_str)
            assert parsed_back == article

    def test_returns_list_of_dicts(self, minimal_article_xml: str) -> None:
        """Return type is list[dict]."""
        result = parse_xml(minimal_article_xml)

        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)


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

    def test_extracts_date(self, complete_article_xml: str) -> None:
        """Date field is extracted in ISO format."""
        result = parse_xml(complete_article_xml)
        article = result[0]

        assert article["date"] == "2024-03-15"

    def test_extracts_pmcid(self, complete_article_xml: str) -> None:
        """PMCID is extracted when present in ArticleIdList."""
        result = parse_xml(complete_article_xml)
        article = result[0]

        assert article["pmcid"] == "PMC1234567"

    def test_extracts_authors(self, complete_article_xml: str) -> None:
        """Authors are extracted as a list."""
        result = parse_xml(complete_article_xml)
        article = result[0]

        assert isinstance(article["authors"], list)
        assert len(article["authors"]) == 2


# =============================================================================
# Authors formatting
# =============================================================================


class TestParseAuthors:
    """Author name formatting: "LastName ForeName"."""

    def test_authors_formatted_as_lastname_forename(self) -> None:
        """Authors are formatted as "LastName ForeName"."""
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

        assert authors[0] == "Smith John"
        assert authors[1] == "Doe Jane"

    def test_author_with_only_lastname_no_trailing_whitespace(self) -> None:
        """Author with only LastName (no ForeName) has no trailing space."""
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
        assert authors[0] == "Smith John"
        assert authors[1] == "OgataK"
        # Explicitly verify no trailing whitespace
        assert not authors[1].endswith(" ")


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

        assert result[0]["authors"][0] == "M\u00fcller Fran\u00e7ois"


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
        # stderr should contain progress info
        assert "Parsed" in captured.err or "article" in captured.err

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
# Date backwards compatibility
# =============================================================================


class TestParseDateBackwardsCompat:
    """Both 'date' and 'year' fields should be present."""

    def test_year_field_present_with_full_date(self) -> None:
        """year field is still present alongside date for backwards compat."""
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
        article = result[0]

        assert "date" in article
        assert "year" in article
        assert article["date"] == "1975-10-27"
        assert article["year"] == 1975

    def test_medlinedate_preserves_year_field(self) -> None:
        """MedlineDate entries still have a year field."""
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

        assert result[0]["year"] == 1975


# =============================================================================
# Date fixtures from files
# =============================================================================


class TestParseDateFixtures:
    """Tests using actual XML fixture files."""

    def test_full_date_fixture(self, date_fixtures_dir: Path) -> None:
        """Fixture file full-date.xml produces 1975-10-27."""
        xml = (date_fixtures_dir / "full-date.xml").read_text()
        # Wrap bare PubmedArticle in PubmedArticleSet if needed
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert len(result) == 1
        assert result[0]["date"] == "1975-10-27"
        assert result[0]["year"] == 1975

    def test_year_month_fixture(self, date_fixtures_dir: Path) -> None:
        """Fixture file year-month.xml produces 1975-06."""
        xml = (date_fixtures_dir / "year-month.xml").read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-06"

    def test_year_only_fixture(self, date_fixtures_dir: Path) -> None:
        """Fixture file year-only.xml produces 1976."""
        xml = (date_fixtures_dir / "year-only.xml").read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert result[0]["date"] == "1976"

    def test_year_season_fixture(self, date_fixtures_dir: Path) -> None:
        """Fixture file year-season.xml: Summer -> 1975-06."""
        xml = (date_fixtures_dir / "year-season.xml").read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-06"

    def test_medlinedate_month_range_fixture(self, date_fixtures_dir: Path) -> None:
        """Fixture medlinedate-month-range.xml: Jul-Aug -> 1975-07."""
        xml = (date_fixtures_dir / "medlinedate-month-range.xml").read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-07"

    def test_medlinedate_day_range_fixture(self, date_fixtures_dir: Path) -> None:
        """Fixture medlinedate-day-range.xml: Jul 4-7 -> 1977-07-04."""
        xml = (date_fixtures_dir / "medlinedate-day-range.xml").read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert result[0]["date"] == "1977-07-04"

    def test_medlinedate_year_range_fixture(self, date_fixtures_dir: Path) -> None:
        """Fixture medlinedate-year-range.xml: 1975-1976 -> 1975."""
        xml = (date_fixtures_dir / "medlinedate-year-range.xml").read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert result[0]["date"] == "1975"

    def test_medlinedate_cross_year_fixture(self, date_fixtures_dir: Path) -> None:
        """Fixture medlinedate-cross-year.xml: 1975 Dec-1976 Jan -> 1975-12."""
        xml = (date_fixtures_dir / "medlinedate-cross-year.xml").read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-12"

    def test_medlinedate_uppercase_fixture(self, date_fixtures_dir: Path) -> None:
        """Fixture medlinedate-uppercase.xml: MAR-APR -> 1975-03."""
        xml = (date_fixtures_dir / "medlinedate-uppercase.xml").read_text()
        if "<PubmedArticleSet>" not in xml:
            xml = f"<PubmedArticleSet>{xml}</PubmedArticleSet>"

        result = parse_xml(xml)

        assert result[0]["date"] == "1975-03"


# =============================================================================
# Streaming parse
# =============================================================================


class TestParseStream:
    """parse_xml_stream should yield articles one at a time."""

    def test_stream_yields_dicts(self, minimal_article_xml: str) -> None:
        """parse_xml_stream yields dict objects."""
        stream = io.StringIO(minimal_article_xml)
        results = list(parse_xml_stream(stream))

        assert len(results) == 1
        assert isinstance(results[0], dict)
        assert results[0]["pmid"] == "12345"

    def test_stream_is_lazy(self, two_articles_xml: str) -> None:
        """parse_xml_stream returns an iterator, not a list."""
        import types

        stream = io.StringIO(two_articles_xml)
        result = parse_xml_stream(stream)

        assert isinstance(result, types.GeneratorType) or hasattr(result, "__next__")


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
        assert article["authors"] == ["Hummerich W", "Krause D K"]

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

        assert len(result) >= 1
        for article in result:
            assert "pmid" in article
            # Must be JSON-serializable
            json.dumps(article)
