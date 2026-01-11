#!/bin/bash
# generate-golden.sh - Generate golden JSONL files using EDirect/xtract
#
# Usage: generate-golden.sh <xml_file> [xml_file...]
# Output: JSONL on stdout (one JSON object per article)
#
# Requires: EDirect tools (xtract) in PATH, jq
#
# This uses NCBI's official xtract tool as the reference implementation
# to generate expected outputs for testing pm-parse.
#
# NOTE: Uses jq for JSON construction to properly handle special characters.
# The previous awk-based approach had bugs with escape sequences.

set -euo pipefail

# Check for xtract in PATH
if ! command -v xtract &> /dev/null; then
    # Try common EDirect location
    if [ -x "${HOME}/edirect/xtract" ]; then
        export PATH="${HOME}/edirect:${PATH}"
    else
        echo "Error: xtract not found. Install EDirect:" >&2
        echo "  sh -c \"\$(curl -fsSL https://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/install-edirect.sh)\"" >&2
        exit 1
    fi
fi

# Check for jq
if ! command -v jq &> /dev/null; then
    echo "Error: jq not found. Install with: apt install jq" >&2
    exit 1
fi

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <xml_file> [xml_file...]" >&2
    exit 1
fi

# Process each XML file
for xml_file in "$@"; do
    if [ ! -f "$xml_file" ]; then
        echo "Warning: File not found: $xml_file" >&2
        continue
    fi

    # Wrap single article in PubmedArticleSet if needed
    full_xml=$(echo "<PubmedArticleSet>"; cat "$xml_file"; echo "</PubmedArticleSet>")

    # Extract PMID
    pmid=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -element MedlineCitation/PMID 2>/dev/null || true)

    # Extract Title
    title=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -element ArticleTitle 2>/dev/null || true)

    # Extract Journal
    journal=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -element "Journal/Title" 2>/dev/null || true)

    # Extract Year (try Year first, then MedlineDate)
    year=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -element "PubDate/Year" 2>/dev/null || true)
    if [ -z "$year" ]; then
        # Try MedlineDate and extract first 4-digit year
        medline_date=$(echo "$full_xml" | xtract -pattern PubmedArticle \
            -element "PubDate/MedlineDate" 2>/dev/null || true)
        if [ -n "$medline_date" ]; then
            year=$(echo "$medline_date" | grep -oE '[0-9]{4}' | head -1)
        fi
    fi

    # Extract DOI
    doi=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -block ArticleId -if "@IdType" -equals doi -element ArticleId 2>/dev/null || true)

    # Extract Abstract (all AbstractText joined with space)
    abstract=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -block Abstract -sep " " -element AbstractText 2>/dev/null || true)

    # Extract Authors (as newline-separated list: "LastName ForeName")
    authors_raw=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -block Author -sep " " -element LastName,ForeName 2>/dev/null || true)

    # Build JSON using jq
    # jq's @json filter properly escapes all special characters
    json=$(jq -n \
        --arg pmid "$pmid" \
        --arg title "$title" \
        --arg journal "$journal" \
        --arg year "$year" \
        --arg doi "$doi" \
        --arg abstract "$abstract" \
        --arg authors_raw "$authors_raw" \
        '
        # Start with pmid (always present)
        {pmid: $pmid}

        # Add optional fields if non-empty
        | if $title != "" then .title = $title else . end
        | if $authors_raw != "" then
            .authors = ($authors_raw | split("\n") | map(select(. != "")))
          else . end
        | if $journal != "" then .journal = $journal else . end
        | if $year != "" then .year = $year else . end
        | if $doi != "" then .doi = $doi else . end
        | if $abstract != "" then .abstract = $abstract else . end
        ')

    # Output as single line (JSONL format)
    echo "$json" | jq -c .
done
