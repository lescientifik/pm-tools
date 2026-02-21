"""Shared fixtures for pm-tools test suite."""

from pathlib import Path

import pytest

# Project root directory
PROJECT_DIR = Path(__file__).parent.parent
FIXTURES_DIR = PROJECT_DIR / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def edge_cases_dir(fixtures_dir: Path) -> Path:
    """Return the path to edge-cases fixtures."""
    return fixtures_dir / "edge-cases"


@pytest.fixture
def date_fixtures_dir(edge_cases_dir: Path) -> Path:
    """Return the path to date fixture XMLs."""
    return edge_cases_dir / "dates"


@pytest.fixture
def minimal_article_xml() -> str:
    """Minimal PubmedArticle XML with only PMID."""
    return """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345</PMID>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""


@pytest.fixture
def complete_article_xml() -> str:
    """Complete PubmedArticle XML with all standard fields."""
    return """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345678</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate><Year>2024</Year><Month>Mar</Month><Day>15</Day></PubDate>
        </JournalIssue>
        <Title>Nature Medicine</Title>
      </Journal>
      <ArticleTitle>Test Article Title</ArticleTitle>
      <Abstract>
        <AbstractText>This is the abstract.</AbstractText>
      </Abstract>
      <AuthorList>
        <Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
        <Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author>
      </AuthorList>
      <ELocationID EIdType="doi" ValidYN="Y">10.1234/test</ELocationID>
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


@pytest.fixture
def two_articles_xml() -> str:
    """Two PubmedArticles in a single PubmedArticleSet."""
    return """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>111</PMID>
    <Article>
      <ArticleTitle>First Article</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
<PubmedArticle>
  <MedlineCitation>
    <PMID>222</PMID>
    <Article>
      <ArticleTitle>Second Article</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""


@pytest.fixture
def structured_abstract_xml() -> str:
    """Article with a structured abstract (labeled sections)."""
    return """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345</PMID>
    <Article>
      <Abstract>
        <AbstractText Label="BACKGROUND">This is background.</AbstractText>
        <AbstractText Label="METHODS">These are methods.</AbstractText>
        <AbstractText Label="RESULTS">These are results.</AbstractText>
      </Abstract>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""


@pytest.fixture
def plain_abstract_xml() -> str:
    """Article with a plain (non-structured) abstract."""
    return """<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345</PMID>
    <Article>
      <Abstract>
        <AbstractText>This is a plain abstract without sections.</AbstractText>
      </Abstract>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""


@pytest.fixture
def mock_esearch_response() -> str:
    """Mock XML response from NCBI esearch API."""
    return """<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE eSearchResult PUBLIC "-//NLM//DTD esearch 20060628//EN"
 "https://eutils.ncbi.nlm.nih.gov/eutils/dtd/20060628/esearch.dtd">
<eSearchResult>
    <Count>3</Count>
    <RetMax>3</RetMax>
    <RetStart>0</RetStart>
    <IdList>
        <Id>12345</Id>
        <Id>67890</Id>
        <Id>11111</Id>
    </IdList>
</eSearchResult>"""


@pytest.fixture
def mock_esearch_empty_response() -> str:
    """Mock XML response from NCBI esearch API with zero results."""
    return """<?xml version="1.0" encoding="UTF-8" ?>
<eSearchResult>
    <Count>0</Count>
    <RetMax>0</RetMax>
    <RetStart>0</RetStart>
    <IdList>
    </IdList>
</eSearchResult>"""


@pytest.fixture
def mock_efetch_response() -> str:
    """Mock XML response from NCBI efetch API."""
    return """<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN"
 "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation>
        <PMID Version="1">12345</PMID>
        <Article>
            <ArticleTitle>Mock Article</ArticleTitle>
        </Article>
    </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""
