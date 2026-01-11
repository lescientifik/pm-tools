#!/bin/bash
# baseline-to-xtract-jsonl.sh - Generate JSONL from XML using xtract (optimized)
#
# Usage: baseline-to-xtract-jsonl.sh <xml_file> [xml_file...]
#        cat file.xml | baseline-to-xtract-jsonl.sh --stdin
# Output: JSONL on stdout (one JSON object per article)
#
# Requires: EDirect tools (xtract) in PATH, jq
#
# This script uses a single xtract call to extract all fields at once,
# making it much faster than per-article processing.
# Handles both single-article fixtures and multi-article baseline files.
# Supports .xml.gz compressed files.

set -euo pipefail

# Check for xtract in PATH
if ! command -v xtract &> /dev/null; then
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
    echo "       cat file.xml | $0 --stdin" >&2
    exit 1
fi

# Placeholder for missing fields (unlikely to appear in real data)
EMPTY_MARKER="___EMPTY___"
# Field separator for authors (unit separator, 0x1F)
AUTHOR_SEP=$'\x1f'

# Extract fields using xtract - outputs 8 tab-separated fields:
# 1:PMID, 2:Title, 3:Journal, 4:Year, 5:MedlineDate, 6:ArticleIds, 7:Abstract, 8:Authors
run_xtract() {
    xtract -pattern PubmedArticle \
        -def "$EMPTY_MARKER" \
        -element MedlineCitation/PMID \
        -element ArticleTitle \
        -element Journal/Title \
        -element PubDate/Year \
        -element PubDate/MedlineDate \
        -sep "|" -element ArticleId \
        -element Abstract/AbstractText \
        -block Author -sep " " -tab "$AUTHOR_SEP" -element LastName,ForeName 2>/dev/null || true
}

# Convert xtract TSV output to JSONL
tsv_to_jsonl() {
    while IFS=$'\t' read -r pmid title journal year medline_date article_ids abstract authors_raw; do
        # Skip if no PMID
        [ -z "$pmid" ] && continue

        # Handle empty marker
        [ "$medline_date" = "$EMPTY_MARKER" ] && medline_date=""
        [ "$abstract" = "$EMPTY_MARKER" ] && abstract=""

        # If no Year, try to extract from MedlineDate
        if [ -z "$year" ] || [ "$year" = "$EMPTY_MARKER" ]; then
            year=""
            if [ -n "$medline_date" ]; then
                year=$(echo "$medline_date" | grep -oE '[0-9]{4}' | head -1 || true)
            fi
        fi

        # Extract DOI from article_ids (pipe-separated, DOI starts with "10.")
        doi=""
        if [ -n "$article_ids" ] && [ "$article_ids" != "$EMPTY_MARKER" ]; then
            doi=$(echo "$article_ids" | tr '|' '\n' | grep -E '^10\.' | head -1 || true)
        fi

        # Split authors by unit separator
        local authors_json="[]"
        if [ -n "$authors_raw" ] && [ "$authors_raw" != "$EMPTY_MARKER" ]; then
            authors_json=$(echo "$authors_raw" | tr "$AUTHOR_SEP" '\n' | jq -R . | jq -s 'map(select(. != ""))')
        fi

        # Build JSON using jq (handles all escaping properly)
        jq -n -c \
            --arg pmid "$pmid" \
            --arg title "$title" \
            --arg journal "$journal" \
            --arg year "$year" \
            --arg doi "$doi" \
            --arg abstract "$abstract" \
            --argjson authors "$authors_json" \
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

# Read file content, handling gzip and wrapping
read_xml() {
    local xml_file="$1"

    # Check if gzipped
    if [[ "$xml_file" == *.gz ]]; then
        zcat "$xml_file"
    else
        cat "$xml_file"
    fi
}

# Wrap single article in PubmedArticleSet if needed
wrap_if_needed() {
    local content
    content=$(cat)

    if echo "$content" | head -5 | grep -q '<PubmedArticleSet'; then
        echo "$content"
    else
        echo "<PubmedArticleSet>"
        echo "$content"
        echo "</PubmedArticleSet>"
    fi
}

# Main processing
if [ "$1" = "--stdin" ]; then
    wrap_if_needed | run_xtract | tsv_to_jsonl
else
    for xml_file in "$@"; do
        if [ ! -f "$xml_file" ]; then
            echo "Warning: File not found: $xml_file" >&2
            continue
        fi
        read_xml "$xml_file" | wrap_if_needed | run_xtract | tsv_to_jsonl
    done
fi
