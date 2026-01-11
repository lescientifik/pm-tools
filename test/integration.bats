#!/usr/bin/env bats

# Integration tests for the full pm-* pipeline

setup() {
    load 'test_helper'

    # Create temporary directory for mocks
    MOCK_DIR="$(mktemp -d)"
    export PATH="${MOCK_DIR}:${PATH}"
}

teardown() {
    rm -rf "$MOCK_DIR"
}

# --- Local pipeline tests (no network) ---

@test "integration: baseline file → pm-parse → valid JSONL" {
    # Given: the baseline file exists
    local baseline="${PROJECT_DIR}/data/pubmed25n0001.xml.gz"
    [ -f "$baseline" ] || skip "Baseline file not found"

    # When: parsing first 100 articles
    run bash -c "zcat '$baseline' | head -10000 | '$PM_PARSE' | head -10"

    # Then: output is valid JSONL
    [ "$status" -eq 0 ]
    [ -n "$output" ]
    # Each line should be valid JSON
    while IFS= read -r line; do
        echo "$line" | jq . > /dev/null || fail "Invalid JSON: $line"
    done <<< "$output"
}

@test "integration: pm-parse output can be filtered with jq" {
    # Given: a parsed article
    local xml='<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345</PMID>
    <Article>
      <Journal><Title>Nature</Title></Journal>
      <ArticleTitle>Test Article</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>'

    # When: parsing and filtering
    run bash -c "echo '$xml' | '$PM_PARSE' | jq -r '.journal'"

    # Then: filter extracts the field
    [ "$status" -eq 0 ]
    [ "$output" = "Nature" ]
}

# --- Mocked full pipeline tests ---

@test "integration: pm-search | pm-fetch | pm-parse pipeline" {
    # Create mock curl that handles both esearch and efetch
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
if [[ "$*" == *"esearch"* ]]; then
    # Mock esearch response
    cat << 'XML'
<?xml version="1.0" ?>
<eSearchResult>
    <Count>1</Count>
    <IdList><Id>12345</Id></IdList>
</eSearchResult>
XML
elif [[ "$*" == *"efetch"* ]]; then
    # Mock efetch response
    cat << 'XML'
<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345</PMID>
    <Article>
      <ArticleTitle>CRISPR Gene Editing</ArticleTitle>
      <Journal><Title>Science</Title></Journal>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>
XML
fi
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"

    # When: running full pipeline
    run bash -c "'$PM_SEARCH' 'CRISPR' | '$PM_FETCH' | '$PM_PARSE'"

    # Then: get valid JSONL output
    [ "$status" -eq 0 ]
    [[ "$output" == *"12345"* ]]
    [[ "$output" == *"CRISPR Gene Editing"* ]]
    [[ "$output" == *"Science"* ]]
}

@test "integration: pipeline handles multiple articles" {
    # Create mock for multiple results
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
if [[ "$*" == *"esearch"* ]]; then
    cat << 'XML'
<?xml version="1.0" ?>
<eSearchResult>
    <Count>2</Count>
    <IdList><Id>111</Id><Id>222</Id></IdList>
</eSearchResult>
XML
elif [[ "$*" == *"efetch"* ]]; then
    cat << 'XML'
<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation><PMID>111</PMID><Article><ArticleTitle>Article One</ArticleTitle></Article></MedlineCitation>
</PubmedArticle>
<PubmedArticle>
  <MedlineCitation><PMID>222</PMID><Article><ArticleTitle>Article Two</ArticleTitle></Article></MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>
XML
fi
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"

    # When: running pipeline
    run bash -c "'$PM_SEARCH' 'test' | '$PM_FETCH' | '$PM_PARSE'"

    # Then: get 2 JSONL lines
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 2 ]
}

@test "integration: pipeline with jq filtering" {
    # Create mock
    cat > "${MOCK_DIR}/curl" << 'MOCK_CURL'
#!/bin/bash
if [[ "$*" == *"esearch"* ]]; then
    cat << 'XML'
<eSearchResult><Count>2</Count><IdList><Id>111</Id><Id>222</Id></IdList></eSearchResult>
XML
elif [[ "$*" == *"efetch"* ]]; then
    cat << 'XML'
<PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID>111</PMID><Article><Journal><Title>Nature</Title></Journal><ArticleTitle>Nature Article</ArticleTitle></Article></MedlineCitation></PubmedArticle>
<PubmedArticle><MedlineCitation><PMID>222</PMID><Article><Journal><Title>Science</Title></Journal><ArticleTitle>Science Article</ArticleTitle></Article></MedlineCitation></PubmedArticle>
</PubmedArticleSet>
XML
fi
MOCK_CURL
    chmod +x "${MOCK_DIR}/curl"

    # When: filtering for Nature articles
    run bash -c "'$PM_SEARCH' 'test' | '$PM_FETCH' | '$PM_PARSE' | jq -r 'select(.journal == \"Nature\") | .title'"

    # Then: only Nature article returned
    [ "$status" -eq 0 ]
    [ "$output" = "Nature Article" ]
}
