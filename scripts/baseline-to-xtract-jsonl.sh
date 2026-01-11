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

# Convert xtract TSV output to JSONL using awk (fast, single pass)
# TSV fields: PMID, Title, Journal, Year, MedlineDate, ArticleIds, Abstract, Authors
tsv_to_jsonl() {
    awk -F'\t' -v empty_marker="$EMPTY_MARKER" -v author_sep="$AUTHOR_SEP" '
function json_escape(s) {
    gsub(/\\/, "\\\\", s)
    gsub(/"/, "\\\"", s)
    gsub(/\n/, "\\n", s)
    gsub(/\r/, "\\r", s)
    gsub(/\t/, "\\t", s)
    return s
}

{
    pmid = $1
    title = $2
    journal = $3
    year = $4
    medline_date = $5
    article_ids = $6
    abstract = $7
    authors_raw = $8

    # Skip if no PMID
    if (pmid == "" || pmid == empty_marker) next

    # Handle empty markers
    if (title == empty_marker) title = ""
    if (journal == empty_marker) journal = ""
    if (year == empty_marker) year = ""
    if (medline_date == empty_marker) medline_date = ""
    if (article_ids == empty_marker) article_ids = ""
    if (abstract == empty_marker) abstract = ""
    if (authors_raw == empty_marker) authors_raw = ""

    # If no Year, try to extract from MedlineDate
    if (year == "" && medline_date != "") {
        if (match(medline_date, /[0-9][0-9][0-9][0-9]/)) {
            year = substr(medline_date, RSTART, 4)
        }
    }

    # Extract DOI from article_ids (pipe-separated, DOI starts with "10.")
    doi = ""
    if (article_ids != "") {
        n = split(article_ids, ids, "|")
        for (i = 1; i <= n; i++) {
            if (ids[i] ~ /^10\./) {
                doi = ids[i]
                break
            }
        }
    }

    # Build authors JSON array
    authors_json = "["
    if (authors_raw != "") {
        n = split(authors_raw, auth, author_sep)
        first = 1
        for (i = 1; i <= n; i++) {
            if (auth[i] != "") {
                if (!first) authors_json = authors_json ","
                authors_json = authors_json "\"" json_escape(auth[i]) "\""
                first = 0
            }
        }
    }
    authors_json = authors_json "]"

    # Build and output JSON
    printf "{\"pmid\":\"%s\"", json_escape(pmid)
    if (title != "") printf ",\"title\":\"%s\"", json_escape(title)
    if (authors_json != "[]") printf ",\"authors\":%s", authors_json
    if (journal != "") printf ",\"journal\":\"%s\"", json_escape(journal)
    if (year != "") printf ",\"year\":\"%s\"", json_escape(year)
    if (doi != "") printf ",\"doi\":\"%s\"", json_escape(doi)
    if (abstract != "") printf ",\"abstract\":\"%s\"", json_escape(abstract)
    print "}"
}
'
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
