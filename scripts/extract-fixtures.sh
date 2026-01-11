#!/bin/bash
#
# extract-fixtures.sh - Extract random and edge-case articles from PubMed baseline XML
#
# Usage:
#   extract-fixtures.sh --baseline FILE --random N --output-dir DIR
#   extract-fixtures.sh --baseline FILE --edge-case TYPE --output-dir DIR
#   extract-fixtures.sh --baseline FILE --all-edge-cases --output-dir DIR
#
# Edge case types: no-doi, no-abstract, structured-abstract, unicode, mesh-terms, errata

set -eu
# Note: we don't use pipefail because awk exits early when done,
# causing zcat to receive SIGPIPE which is expected behavior

# --- Usage ---
usage() {
    cat >&2 <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --baseline FILE      Path to baseline .xml.gz file (required)
  --random N           Extract N random articles
  --edge-case TYPE     Find one article matching edge case TYPE
  --all-edge-cases     Find articles for all known edge cases
  --output-dir DIR     Output directory (required)
  --help               Show this help

Edge case types:
  no-doi              Article without DOI
  no-abstract         Article without abstract
  structured-abstract Article with labeled AbstractText sections
  unicode             Article with non-ASCII characters in title/abstract
  mesh-terms          Article with MeSH terms
  errata              Article with corrections/errata

Examples:
  $(basename "$0") --baseline data/pubmed25n0001.xml.gz --random 5 --output-dir fixtures/random
  $(basename "$0") --baseline data/pubmed25n0001.xml.gz --edge-case no-doi --output-dir fixtures/edge-cases
  $(basename "$0") --baseline data/pubmed25n0001.xml.gz --all-edge-cases --output-dir fixtures/edge-cases
EOF
    exit 1
}

# --- Helpers ---
die() {
    echo "Error: $*" >&2
    exit 1
}

# Count total articles in baseline (fast with grep -c)
count_articles() {
    local baseline="$1"
    zcat "$baseline" 2>/dev/null | grep -c '<PubmedArticle>' || echo "0"
}

# Extract article at specific index using awk (fast single-pass)
extract_article_by_index() {
    local baseline="$1"
    local index="$2"

    zcat "$baseline" 2>/dev/null | awk -v idx="$index" '
        /<PubmedArticle>/ {
            count++
            if (count == idx) in_article = 1
        }
        in_article { print }
        /<\/PubmedArticle>/ && in_article { exit }
    '
}

# Extract multiple articles by indices (single pass, much faster)
extract_articles_by_indices() {
    local baseline="$1"
    local output_dir="$2"
    shift 2
    local indices="$*"

    mkdir -p "$output_dir"

    zcat "$baseline" 2>/dev/null | awk -v indices="$indices" -v outdir="$output_dir" '
        BEGIN {
            n = split(indices, idx_arr, " ")
            for (i = 1; i <= n; i++) {
                target[idx_arr[i]] = 1
            }
        }
        /<PubmedArticle>/ {
            count++
            if (count in target) {
                in_article = 1
                article = ""
                pmid = ""
            }
        }
        in_article {
            article = article $0 "\n"
        }
        /<PMID[^>]*>/ && in_article && pmid == "" {
            # Extract PMID using gsub (mawk compatible)
            line = $0
            gsub(/.*<PMID[^>]*>/, "", line)
            gsub(/<\/PMID>.*/, "", line)
            pmid = line
        }
        /<\/PubmedArticle>/ && in_article {
            in_article = 0
            if (pmid == "") pmid = "unknown-" count
            filename = outdir "/pmid-" pmid ".xml"
            printf "%s", article > filename
            close(filename)
            print "Saved: " filename > "/dev/stderr"
            pmid = ""
            extracted++
            delete target[count]
            # Exit early if all found
            remaining = 0
            for (k in target) remaining++
            if (remaining == 0) exit
        }
    '
}

# Find and extract first article matching an edge case pattern (single pass)
find_edge_case() {
    local baseline="$1"
    local case_type="$2"
    local output_dir="$3"
    local max_scan="${4:-10000}"

    mkdir -p "$output_dir"

    # Validate edge case type
    case "$case_type" in
        no-doi|no-abstract|structured-abstract|unicode|mesh-terms|errata) ;;
        *) die "Unknown edge case type: $case_type" ;;
    esac

    zcat "$baseline" 2>/dev/null | awk -v condition="$case_type" -v outdir="$output_dir" -v maxscan="$max_scan" '
        /<PubmedArticle>/ {
            count++
            in_article = 1
            article = ""
            pmid = ""
        }
        in_article {
            article = article $0 "\n"
        }
        /<PMID[^>]*>/ && in_article && pmid == "" {
            # Extract PMID using gsub (mawk compatible)
            line = $0
            gsub(/.*<PMID[^>]*>/, "", line)
            gsub(/<\/PMID>.*/, "", line)
            pmid = line
        }
        /<\/PubmedArticle>/ && in_article {
            in_article = 0
            found = 0

            if (condition == "no-doi") {
                if (index(article, "IdType=\"doi\"") == 0) found = 1
            } else if (condition == "no-abstract") {
                if (index(article, "<Abstract>") == 0) found = 1
            } else if (condition == "structured-abstract") {
                if (index(article, "<AbstractText") > 0 && index(article, "Label=") > 0) found = 1
            } else if (condition == "unicode") {
                # Check for HTML entities (common in PubMed for special chars)
                if (index(article, "&") > 0) found = 1
            } else if (condition == "mesh-terms") {
                if (index(article, "<MeshHeadingList>") > 0) found = 1
            } else if (condition == "errata") {
                if (index(article, "<CommentsCorrections") > 0 || index(article, "<Errat") > 0) found = 1
            }

            if (found) {
                if (pmid == "") pmid = "unknown-" count
                filename = outdir "/pmid-" pmid ".xml"
                printf "%s", article > filename
                close(filename)
                print "Saved: " filename > "/dev/stderr"
                exit 0
            }

            if (count >= maxscan) {
                print "Warning: Could not find " condition " after scanning " maxscan " articles" > "/dev/stderr"
                exit 0
            }
        }
    '
}

# --- Main extraction functions ---

extract_random() {
    local baseline="$1"
    local n="$2"
    local output_dir="$3"

    local total
    total=$(count_articles "$baseline")
    if [ "$total" -eq 0 ]; then
        die "No articles found in baseline"
    fi

    echo "Extracting $n random articles from $total total..." >&2

    # Generate N random indices (sorted for single-pass extraction)
    local indices
    indices=$(shuf -i 1-"$total" -n "$n" | sort -n | tr '\n' ' ')

    # shellcheck disable=SC2086 # Intentional word splitting for indices
    extract_articles_by_indices "$baseline" "$output_dir" $indices
}

extract_edge_case() {
    local baseline="$1"
    local case_type="$2"
    local output_dir="$3"

    echo "Searching for edge case: $case_type..." >&2
    find_edge_case "$baseline" "$case_type" "$output_dir"
}

extract_all_edge_cases() {
    local baseline="$1"
    local output_dir="$2"

    local edge_cases=("no-doi" "no-abstract" "structured-abstract" "unicode" "mesh-terms" "errata")

    for case_type in "${edge_cases[@]}"; do
        extract_edge_case "$baseline" "$case_type" "$output_dir/$case_type"
    done
}

# --- Main ---

main() {
    local baseline=""
    local random_count=""
    local edge_case=""
    local all_edge_cases=0
    local output_dir=""

    while [ $# -gt 0 ]; do
        case "$1" in
            --baseline)
                baseline="$2"
                shift 2
                ;;
            --random)
                random_count="$2"
                shift 2
                ;;
            --edge-case)
                edge_case="$2"
                shift 2
                ;;
            --all-edge-cases)
                all_edge_cases=1
                shift
                ;;
            --output-dir)
                output_dir="$2"
                shift 2
                ;;
            --help|-h)
                usage
                ;;
            *)
                die "Unknown option: $1"
                ;;
        esac
    done

    # Validate arguments
    [ -z "$baseline" ] && usage
    [ -z "$output_dir" ] && usage
    [ ! -f "$baseline" ] && die "Baseline file not found: $baseline"

    # Execute requested operation
    if [ -n "$random_count" ]; then
        extract_random "$baseline" "$random_count" "$output_dir"
    elif [ -n "$edge_case" ]; then
        extract_edge_case "$baseline" "$edge_case" "$output_dir"
    elif [ "$all_edge_cases" -eq 1 ]; then
        extract_all_edge_cases "$baseline" "$output_dir"
    else
        usage
    fi
}

# Run if not sourced
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
