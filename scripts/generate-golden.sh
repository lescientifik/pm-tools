#!/bin/bash
# generate-golden.sh - Generate golden JSONL files using EDirect/xtract
#
# Usage: generate-golden.sh <xml_file> [xml_file...]
# Output: JSONL on stdout (one JSON object per article)
#
# Requires: EDirect tools (xtract) in PATH
#
# This uses NCBI's official xtract tool as the reference implementation
# to generate expected outputs for testing pm-parse.

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

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <xml_file> [xml_file...]" >&2
    exit 1
fi

# JSON escape function in awk
json_escape_awk='
function json_escape(s) {
    gsub(/\\/, "\\\\", s)
    gsub(/"/, "\\\"", s)
    gsub(/\n/, "\\n", s)
    gsub(/\r/, "\\r", s)
    gsub(/\t/, "\\t", s)
    return s
}
'

# Process each XML file
for xml_file in "$@"; do
    if [ ! -f "$xml_file" ]; then
        echo "Warning: File not found: $xml_file" >&2
        continue
    fi

    # Wrap single article in PubmedArticleSet if needed
    full_xml=$(echo "<PubmedArticleSet>"; cat "$xml_file"; echo "</PubmedArticleSet>")

    # Extract basic fields + authors (tab-separated)
    # Fields: PMID, Title, Journal, Year, Author1, Author2, ...
    basic=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -element MedlineCitation/PMID ArticleTitle "Journal/Title" "PubDate/Year" \
        -block Author -sep " " -element LastName,ForeName)

    # Extract DOI separately
    doi=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -block ArticleId -if "@IdType" -equals doi -element ArticleId 2>/dev/null || true)

    # Extract Abstract (all AbstractText joined with space)
    abstract=$(echo "$full_xml" | xtract -pattern PubmedArticle \
        -block Abstract -sep " " -element AbstractText 2>/dev/null || true)

    # Build JSONL using awk
    echo "$basic" | awk -F'\t' -v doi="$doi" -v abstract="$abstract" "
    $json_escape_awk
    {
        pmid = json_escape(\$1)
        title = json_escape(\$2)
        journal = json_escape(\$3)
        year = json_escape(\$4)
        doi_val = json_escape(doi)
        abstract_val = json_escape(abstract)

        # Build JSON
        printf \"{\\\"pmid\\\":\\\"%s\\\"\", pmid

        if (title != \"\") printf \",\\\"title\\\":\\\"%s\\\"\", title

        # Build authors array (fields 5+)
        if (NF >= 5) {
            printf \",\\\"authors\\\":[\"
            for (i = 5; i <= NF; i++) {
                author = json_escape(\$i)
                if (i > 5) printf \",\"
                printf \"\\\"%s\\\"\", author
            }
            printf \"]\"
        }

        if (journal != \"\") printf \",\\\"journal\\\":\\\"%s\\\"\", journal
        if (year != \"\") printf \",\\\"year\\\":\\\"%s\\\"\", year
        if (doi_val != \"\") printf \",\\\"doi\\\":\\\"%s\\\"\", doi_val
        if (abstract_val != \"\") printf \",\\\"abstract\\\":\\\"%s\\\"\", abstract_val

        print \"}\"
    }
    "
done
