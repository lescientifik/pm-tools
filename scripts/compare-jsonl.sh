#!/bin/bash
# compare-jsonl.sh - Compare two JSONL files field by field
#
# Usage: compare-jsonl.sh <file1.jsonl> <file2.jsonl>
# Output: Summary of differences
# Exit: 0 if identical, 1 if differences found
#
# Requires: jq
#
# Compares JSONL files by PMID, reporting:
# - Records present in file1 but missing in file2
# - Records present in file2 but missing in file1
# - Field-level differences for matching records

set -euo pipefail

# Check for jq
if ! command -v jq &> /dev/null; then
    echo "Error: jq not found. Install with: apt install jq" >&2
    exit 1
fi

# Check arguments
if [ $# -ne 2 ]; then
    echo "Usage: $0 <file1.jsonl> <file2.jsonl>" >&2
    exit 1
fi

FILE1="$1"
FILE2="$2"

# Verify files exist
if [ ! -f "$FILE1" ]; then
    echo "Error: File not found: $FILE1" >&2
    exit 1
fi

if [ ! -f "$FILE2" ]; then
    echo "Error: File not found: $FILE2" >&2
    exit 1
fi

# Create temp directory for intermediate files
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Index records by PMID
# Creates files like: tmp/file1/12345.json containing the full JSON for PMID 12345
index_by_pmid() {
    local input_file="$1"
    local output_dir="$2"
    mkdir -p "$output_dir"

    while IFS= read -r line || [ -n "$line" ]; do
        if [ -z "$line" ]; then
            continue
        fi
        pmid=$(echo "$line" | jq -r '.pmid // empty')
        if [ -n "$pmid" ]; then
            echo "$line" > "$output_dir/${pmid}.json"
        fi
    done < "$input_file"
}

# Index both files
echo "Indexing records..." >&2
index_by_pmid "$FILE1" "$TMP_DIR/file1"
index_by_pmid "$FILE2" "$TMP_DIR/file2"

# Count records
COUNT1=$(find "$TMP_DIR/file1" -name "*.json" 2>/dev/null | wc -l)
COUNT2=$(find "$TMP_DIR/file2" -name "*.json" 2>/dev/null | wc -l)

echo "File 1: $COUNT1 records" >&2
echo "File 2: $COUNT2 records" >&2

# Track differences
DIFF_COUNT=0
MISSING_IN_2=0
EXTRA_IN_2=0
declare -A FIELD_DIFFS

# Find records in file1 missing from file2
for f in "$TMP_DIR/file1"/*.json; do
    [ -e "$f" ] || continue
    pmid=$(basename "$f" .json)
    if [ ! -f "$TMP_DIR/file2/${pmid}.json" ]; then
        ((MISSING_IN_2++)) || true
        ((DIFF_COUNT++)) || true
        if [ "$MISSING_IN_2" -le 5 ]; then
            echo "missing in file2: PMID $pmid"
        fi
    fi
done

# Find records in file2 not in file1
for f in "$TMP_DIR/file2"/*.json; do
    [ -e "$f" ] || continue
    pmid=$(basename "$f" .json)
    if [ ! -f "$TMP_DIR/file1/${pmid}.json" ]; then
        ((EXTRA_IN_2++)) || true
        ((DIFF_COUNT++)) || true
        if [ "$EXTRA_IN_2" -le 5 ]; then
            echo "extra in file2: PMID $pmid"
        fi
    fi
done

# Compare matching records field by field
FIELDS=("pmid" "title" "authors" "journal" "year" "doi" "abstract")

for f in "$TMP_DIR/file1"/*.json; do
    [ -e "$f" ] || continue
    pmid=$(basename "$f" .json)

    # Skip if not in file2
    if [ ! -f "$TMP_DIR/file2/${pmid}.json" ]; then
        continue
    fi

    json1=$(cat "$f")
    json2=$(cat "$TMP_DIR/file2/${pmid}.json")

    for field in "${FIELDS[@]}"; do
        val1=$(echo "$json1" | jq -r ".$field // empty" | jq -Rs '.')
        val2=$(echo "$json2" | jq -r ".$field // empty" | jq -Rs '.')

        if [ "$val1" != "$val2" ]; then
            ((DIFF_COUNT++)) || true
            FIELD_DIFFS[$field]=$((${FIELD_DIFFS[$field]:-0} + 1))

            # Show first few differences per field
            if [ "${FIELD_DIFFS[$field]}" -le 3 ]; then
                echo "PMID $pmid: $field differs"
                echo "  file1: $(echo "$json1" | jq -c ".$field // null")"
                echo "  file2: $(echo "$json2" | jq -c ".$field // null")"
            fi
        fi
    done
done

# Summary
echo "" >&2
echo "=== Summary ===" >&2

if [ "$DIFF_COUNT" -eq 0 ]; then
    echo "Files are identical (0 differences)"
    exit 0
fi

echo "Total differences: $DIFF_COUNT"

if [ "$MISSING_IN_2" -gt 0 ]; then
    echo "Records missing in file2: $MISSING_IN_2"
fi

if [ "$EXTRA_IN_2" -gt 0 ]; then
    echo "Records extra in file2: $EXTRA_IN_2"
fi

for field in "${FIELDS[@]}"; do
    count="${FIELD_DIFFS[$field]:-0}"
    if [ "$count" -gt 0 ]; then
        echo "Field '$field' differences: $count"
    fi
done

exit 1
