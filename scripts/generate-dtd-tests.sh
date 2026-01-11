#!/bin/bash
# generate-dtd-tests.sh - Generate bats tests from mapping.json
#
# Usage: generate-dtd-tests.sh <mapping.json>
# Output: bats test file on stdout that verifies pm-parse extracts each field

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <mapping.json>" >&2
    exit 1
fi

MAPPING_FILE="$1"

if [ ! -f "$MAPPING_FILE" ]; then
    echo "Error: mapping file not found: $MAPPING_FILE" >&2
    exit 1
fi

# Generate bats file header
cat <<'HEADER'
#!/usr/bin/env bats

# Auto-generated tests from mapping.json
# Verifies pm-parse extracts all mapped fields correctly

setup() {
    export PROJECT_DIR="${BATS_TEST_DIRNAME}/../.."
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

HEADER

# Generate a test for each main field in the mapping
# Filter to main fields only (exclude sub-fields like author_lastname)
jq -r 'to_entries | .[] | select(.key | test("^(pmid|title|authors|journal|year|doi|abstract)$")) | "\(.key)\t\(.value)"' "$MAPPING_FILE" | \
while IFS=$'\t' read -r field xpath; do
    cat <<EOF

@test "pm-parse extracts $field field" {
    # Given: sample XML with $field data
    # XPath: $xpath

    # When: parsing the XML
    result=\$(echo "\$SAMPLE_XML" | "\$PM_PARSE")

    # Then: $field should be present in output
    echo "\$result" | jq -e '.$field' >/dev/null
}
EOF
done
