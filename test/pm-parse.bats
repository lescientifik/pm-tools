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

# --- Baseline non-regression tests ---

@test "pm-parse: parses entire baseline without crashing" {
    # Given: full baseline file with 30000 articles
    local baseline="${PROJECT_DIR}/data/pubmed25n0001.xml.gz"
    [ -f "$baseline" ] || skip "Baseline file not found"

    # When: parsing entire baseline
    run bash -c "zcat '$baseline' | '$PM_PARSE' | wc -l"

    # Then: exits successfully and produces exactly 30000 lines
    [ "$status" -eq 0 ]
    [ "$output" -eq 30000 ]
}

@test "pm-parse: baseline performance > 1000 articles/second" {
    # Given: full baseline file
    local baseline="${PROJECT_DIR}/data/pubmed25n0001.xml.gz"
    [ -f "$baseline" ] || skip "Baseline file not found"

    # When: timing the parse
    local start end elapsed rate
    start=$(date +%s.%N)
    zcat "$baseline" | "$PM_PARSE" > /dev/null
    end=$(date +%s.%N)

    # Then: performance should be > 1000 articles/second
    elapsed=$(echo "$end - $start" | bc)
    rate=$(echo "30000 / $elapsed" | bc)

    # Log performance for visibility
    echo "# Performance: $rate articles/second (${elapsed}s for 30000 articles)" >&3

    # Assert minimum performance threshold
    [ "$rate" -ge 1000 ]
}

# --- Special characters edge cases (Phase 0.7.4) ---

@test "pm-parse: handles quotes and backslashes correctly" {
    # Given: XML with quotes and backslashes
    local xml_file="${FIXTURES_DIR}/edge-cases/special-chars/quotes-backslash.xml"
    [ -f "$xml_file" ] || skip "Fixture not found"

    # When: parsing
    run "$PM_PARSE" < "$xml_file"

    # Then: output is valid JSON
    [ "$status" -eq 0 ]
    echo "$output" | jq . > /dev/null

    # And: title contains properly escaped quotes and backslashes
    local title
    title=$(echo "$output" | jq -r '.title')
    [[ "$title" == *'"quoted text"'* ]]
    [[ "$title" == *'C:\path\to\file'* ]]
}

@test "pm-parse: preserves unicode and control characters" {
    # Given: XML with unicode and control characters
    local xml_file="${FIXTURES_DIR}/edge-cases/special-chars/unicode-control.xml"
    [ -f "$xml_file" ] || skip "Fixture not found"

    # When: parsing
    run "$PM_PARSE" < "$xml_file"

    # Then: output is valid JSON
    [ "$status" -eq 0 ]
    echo "$output" | jq . > /dev/null

    # And: unicode characters are preserved
    local title
    title=$(echo "$output" | jq -r '.title')
    [[ "$title" == *'Müller'* ]]
    [[ "$title" == *'日本語'* ]]

    # And: authors include unicode names
    local first_author
    first_author=$(echo "$output" | jq -r '.authors[0]')
    [[ "$first_author" == *'Müller'* ]]
}

# --- Golden file comparison tests (Phase 0.7.5) ---

@test "pm-parse: output matches golden files for special-chars fixtures" {
    local fixtures=(
        "special-chars/quotes-backslash"
        "special-chars/unicode-control"
    )

    for fixture in "${fixtures[@]}"; do
        local xml_file="${FIXTURES_DIR}/edge-cases/${fixture}.xml"
        local golden_file="${FIXTURES_DIR}/expected/${fixture}.jsonl"
        [ -f "$xml_file" ] || continue
        [ -f "$golden_file" ] || continue

        local actual golden
        actual=$("$PM_PARSE" < "$xml_file" | jq -cS .)
        golden=$(jq -cS . < "$golden_file")

        if [ "$actual" != "$golden" ]; then
            echo "Mismatch for $fixture:"
            echo "Expected: $golden"
            echo "Actual: $actual"
            return 1
        fi
    done
}
