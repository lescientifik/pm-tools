#!/usr/bin/env bats

# Tests for bin/pm-parse - XML to JSONL converter

setup() {
    load 'test_helper'
}

# --- Empty/edge case tests ---

@test "pm-parse exists and is executable" {
    [ -x "$PM_PARSE" ]
}

@test "pm-parse: empty input produces empty output" {
    # Given: empty input
    # When: parsing
    result=$(echo "" | "$PM_PARSE")

    # Then: output is empty
    [ -z "$result" ]
}

@test "pm-parse: whitespace-only input produces empty output" {
    # Given: whitespace only
    # When: parsing
    result=$(echo "   " | "$PM_PARSE")

    # Then: output is empty
    [ -z "$result" ]
}

# --- Minimal article tests ---

@test "pm-parse: extracts PMID from minimal article" {
    # Given: minimal XML with only PMID
    local xml='<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345</PMID>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>'

    # When: parsing
    run bash -c "echo '$xml' | '$PM_PARSE'"

    # Then: PMID is extracted
    [ "$status" -eq 0 ]
    [[ $(echo "$output" | jq -r '.pmid') == "12345" ]]
}

@test "pm-parse: outputs valid JSON" {
    # Given: minimal article
    local xml='<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99999</PMID>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>'

    # When: parsing
    result=$(echo "$xml" | "$PM_PARSE")

    # Then: output is valid JSON
    echo "$result" | jq . >/dev/null
}

# --- Complete article tests ---

@test "pm-parse: extracts all fields from complete article" {
    # Given: complete article with all fields
    local xml='<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345678</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate><Year>2024</Year></PubDate>
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
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList>
      <ArticleId IdType="doi">10.1234/test</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>'

    # When: parsing
    result=$(echo "$xml" | "$PM_PARSE")

    # Then: all fields are present
    [[ $(echo "$result" | jq -r '.pmid') == "12345678" ]]
    [[ $(echo "$result" | jq -r '.title') == "Test Article Title" ]]
    [[ $(echo "$result" | jq -r '.journal') == "Nature Medicine" ]]
    [[ $(echo "$result" | jq -r '.year') == "2024" ]]
    [[ $(echo "$result" | jq -r '.doi') == "10.1234/test" ]]
    [[ $(echo "$result" | jq -r '.abstract') == "This is the abstract." ]]
}

@test "pm-parse: authors are formatted as array" {
    # Given: article with multiple authors
    local xml='<PubmedArticleSet>
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
</PubmedArticleSet>'

    # When: parsing
    result=$(echo "$xml" | "$PM_PARSE")

    # Then: authors is an array with formatted names
    [ "$(echo "$result" | jq -r '.authors | length')" -eq 2 ]
    [[ $(echo "$result" | jq -r '.authors[0]') == "Smith John" ]]
    [[ $(echo "$result" | jq -r '.authors[1]') == "Doe Jane" ]]
}

# --- Multiple articles test ---

@test "pm-parse: multiple articles produce multiple lines" {
    # Given: two articles
    local xml='<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation><PMID>111</PMID></MedlineCitation>
</PubmedArticle>
<PubmedArticle>
  <MedlineCitation><PMID>222</PMID></MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>'

    # When: parsing
    result=$(echo "$xml" | "$PM_PARSE")

    # Then: two lines of output
    line_count=$(echo "$result" | wc -l)
    [ "$line_count" -eq 2 ]

    # And each line has correct PMID
    [[ $(echo "$result" | head -1 | jq -r '.pmid') == "111" ]]
    [[ $(echo "$result" | tail -1 | jq -r '.pmid') == "222" ]]
}

# --- Unicode and special characters ---

@test "pm-parse: handles unicode characters" {
    # Given: article with unicode
    local xml='<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>456</PMID>
    <Article>
      <ArticleTitle>Étude française: naïve résumé</ArticleTitle>
      <AuthorList>
        <Author><LastName>Müller</LastName><ForeName>François</ForeName></Author>
      </AuthorList>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>'

    # When: parsing
    result=$(echo "$xml" | "$PM_PARSE")

    # Then: unicode is preserved
    [[ $(echo "$result" | jq -r '.title') == "Étude française: naïve résumé" ]]
    [[ $(echo "$result" | jq -r '.authors[0]') == "Müller François" ]]
}

@test "pm-parse: handles XML entities" {
    # Given: article with HTML entities
    local xml='<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>789</PMID>
    <Article>
      <ArticleTitle>Effects of A &amp; B on C &lt; D</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>'

    # When: parsing
    result=$(echo "$xml" | "$PM_PARSE")

    # Then: entities are decoded
    [[ $(echo "$result" | jq -r '.title') == "Effects of A & B on C < D" ]]
}

# --- Real fixture test ---

@test "pm-parse: parses real fixture file correctly" {
    # Given: real fixture from baseline
    local fixture_file="${FIXTURES_DIR}/random/pmid-11586.xml"
    [ -f "$fixture_file" ] || skip "Fixture not found"

    # When: parsing (wrap in PubmedArticleSet if needed)
    result=$(cat "$fixture_file" | "$PM_PARSE")

    # Then: output is valid JSONL with expected fields
    echo "$result" | jq -e '.pmid' >/dev/null
    [ "$(echo "$result" | wc -l)" -ge 1 ]
}

# --- Missing fields handling ---

@test "pm-parse: handles missing optional fields gracefully" {
    # Given: article without DOI or abstract
    local xml='<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>999</PMID>
    <Article>
      <ArticleTitle>Title Only</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>'

    # When: parsing
    result=$(echo "$xml" | "$PM_PARSE")

    # Then: required fields present, optional fields null or empty
    [[ $(echo "$result" | jq -r '.pmid') == "999" ]]
    [[ $(echo "$result" | jq -r '.title') == "Title Only" ]]
    # DOI and abstract should be null or empty, not cause error
    echo "$result" | jq . >/dev/null
}
