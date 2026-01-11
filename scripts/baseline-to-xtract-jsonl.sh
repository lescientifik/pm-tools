#!/bin/bash
# baseline-to-xtract-jsonl.sh - Generate JSONL from XML using xtract (optimized)
#
# Usage: baseline-to-xtract-jsonl.sh <xml_file> [xml_file...]
#        baseline-to-xtract-jsonl.sh --stdin < input.xml
# Output: JSONL on stdout (one JSON object per article)
#
# Requires: EDirect tools (xtract) in PATH, jq
#
# This script uses a single xtract call to extract all fields at once,
# making it ~100x faster than generate-golden.sh for large files.

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
    echo "       $0 --stdin < input.xml" >&2
    exit 1
fi

# Use ASCII unit separator (0x1F) as field delimiter within records
# This is unlikely to appear in actual data
FIELD_SEP=$'\x1f'

# Process XML input and convert to JSONL
process_xml() {
    local input_xml="$1"

    # Extract all fields at once using xtract
    # Fields: PMID | Title | Journal | Year | DOI | Abstract | Authors
    # Authors are tab-separated within the field
    #
    # Note: We use -def "" to output empty strings for missing fields
    # and -sep " " to join multiple AbstractText elements
    echo "$input_xml" | xtract -pattern PubmedArticle \
        -def "" \
        -element MedlineCitation/PMID \
        -element ArticleTitle \
        -element "Journal/Title" \
        -element "PubDate/Year" \
        -block ArticleId -if "@IdType" -equals doi -element ArticleId \
        -block Abstract -sep " " -element AbstractText \
        -block Author -sep " " -tab "${FIELD_SEP}" -element LastName,ForeName 2>/dev/null |
    while IFS=$'\t' read -r pmid title journal year doi abstract authors_raw; do
        # Handle MedlineDate if Year is empty
        if [ -z "$year" ]; then
            medline_date=$(echo "$input_xml" | xtract -pattern PubmedArticle \
                -element "PubDate/MedlineDate" 2>/dev/null || true)
            if [ -n "$medline_date" ]; then
                year=$(echo "$medline_date" | grep -oE '[0-9]{4}' | head -1)
            fi
        fi

        # Split authors by field separator
        # Each author is "LastName ForeName"
        IFS="${FIELD_SEP}" read -ra author_array <<< "$authors_raw"

        # Build JSON using jq (handles all escaping properly)
        jq -n -c \
            --arg pmid "$pmid" \
            --arg title "$title" \
            --arg journal "$journal" \
            --arg year "$year" \
            --arg doi "$doi" \
            --arg abstract "$abstract" \
            --argjson authors "$(printf '%s\n' "${author_array[@]}" | jq -R . | jq -s 'map(select(. != ""))')" \
            '
            {pmid: $pmid}
            | if $title != "" then .title = $title else . end
            | if ($authors | length) > 0 then .authors = $authors else . end
            | if $journal != "" then .journal = $journal else . end
            | if $year != "" then .year = $year else . end
            | if $doi != "" then .doi = $doi else . end
            | if $abstract != "" then .abstract = $abstract else . end
            '
    done
}

# Main processing
if [ "$1" = "--stdin" ]; then
    # Read from stdin
    input_xml=$(cat)
    process_xml "$input_xml"
else
    # Process each XML file
    for xml_file in "$@"; do
        if [ ! -f "$xml_file" ]; then
            echo "Warning: File not found: $xml_file" >&2
            continue
        fi

        # Read file and wrap in PubmedArticleSet if needed
        input_xml=$(echo "<PubmedArticleSet>"; cat "$xml_file"; echo "</PubmedArticleSet>")
        process_xml "$input_xml"
    done
fi
