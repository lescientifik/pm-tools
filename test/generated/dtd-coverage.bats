#!/usr/bin/env bats

# Auto-generated tests from mapping.json
# Verifies pm-parse extracts all mapped fields correctly

setup() {
    export PROJECT_DIR="${BATS_TEST_DIRNAME}/.."
    export PM_PARSE="${PROJECT_DIR}/bin/pm-parse"

    # Sample XML with all fields populated
    export SAMPLE_XML='<?xml version="1.0"?>
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345678</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate><Year>2024</Year></PubDate>
        </JournalIssue>
        <Title>Nature Medicine</Title>
        <ISOAbbreviation>Nat Med</ISOAbbreviation>
      </Journal>
      <ArticleTitle>Test Article Title</ArticleTitle>
      <Abstract>
        <AbstractText>This is the abstract text.</AbstractText>
      </Abstract>
      <AuthorList>
        <Author><LastName>Smith</LastName><ForeName>John</ForeName><Initials>J</Initials></Author>
        <Author><LastName>Doe</LastName><ForeName>Jane</ForeName><Initials>J</Initials></Author>
      </AuthorList>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList>
      <ArticleId IdType="pubmed">12345678</ArticleId>
      <ArticleId IdType="doi">10.1234/test.2024</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>'
}


@test "pm-parse extracts pmid field" {
    # Given: sample XML with pmid data
    # XPath: /PubmedArticle/MedlineCitation/PMID

    # When: parsing the XML
    result=$(echo "$SAMPLE_XML" | "$PM_PARSE")

    # Then: pmid should be present in output
    echo "$result" | jq -e '.pmid' >/dev/null
}

@test "pm-parse extracts title field" {
    # Given: sample XML with title data
    # XPath: /PubmedArticle/MedlineCitation/Article/ArticleTitle

    # When: parsing the XML
    result=$(echo "$SAMPLE_XML" | "$PM_PARSE")

    # Then: title should be present in output
    echo "$result" | jq -e '.title' >/dev/null
}

@test "pm-parse extracts authors field" {
    # Given: sample XML with authors data
    # XPath: /PubmedArticle/MedlineCitation/Article/AuthorList/Author

    # When: parsing the XML
    result=$(echo "$SAMPLE_XML" | "$PM_PARSE")

    # Then: authors should be present in output
    echo "$result" | jq -e '.authors' >/dev/null
}

@test "pm-parse extracts journal field" {
    # Given: sample XML with journal data
    # XPath: /PubmedArticle/MedlineCitation/Article/Journal/Title

    # When: parsing the XML
    result=$(echo "$SAMPLE_XML" | "$PM_PARSE")

    # Then: journal should be present in output
    echo "$result" | jq -e '.journal' >/dev/null
}

@test "pm-parse extracts year field" {
    # Given: sample XML with year data
    # XPath: /PubmedArticle/MedlineCitation/Article/Journal/JournalIssue/PubDate/Year

    # When: parsing the XML
    result=$(echo "$SAMPLE_XML" | "$PM_PARSE")

    # Then: year should be present in output
    echo "$result" | jq -e '.year' >/dev/null
}

@test "pm-parse extracts doi field" {
    # Given: sample XML with doi data
    # XPath: /PubmedArticle/PubmedData/ArticleIdList/ArticleId[@IdType='doi']

    # When: parsing the XML
    result=$(echo "$SAMPLE_XML" | "$PM_PARSE")

    # Then: doi should be present in output
    echo "$result" | jq -e '.doi' >/dev/null
}

@test "pm-parse extracts abstract field" {
    # Given: sample XML with abstract data
    # XPath: /PubmedArticle/MedlineCitation/Article/Abstract/AbstractText

    # When: parsing the XML
    result=$(echo "$SAMPLE_XML" | "$PM_PARSE")

    # Then: abstract should be present in output
    echo "$result" | jq -e '.abstract' >/dev/null
}
