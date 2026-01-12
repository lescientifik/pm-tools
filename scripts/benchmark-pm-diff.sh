#!/usr/bin/env bash
# benchmark-pm-diff.sh - Performance test for pm-diff with large files
#
# Tests pm-diff with article collections to measure performance.
#
# NOTE: The current shell/jq implementation is not optimized for large files.
# ~1000 articles takes ~30-50 seconds. For 30k articles target (<30s),
# a rewrite in Python/awk or single-pass jq would be needed.
#
# For now, pm-diff is suitable for:
# - Small comparisons (< 1000 articles)
# - One-off validation checks
# - Piping with --format added/removed (PMID lists)
#
# Usage: ./scripts/benchmark-pm-diff.sh [article_count]
#        Default: 100 articles (quick test)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PM_DIFF="$PROJECT_DIR/bin/pm-diff"

# Default to 100 articles for quick test (see header notes about performance)
ARTICLE_COUNT="${1:-100}"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "=== pm-diff Performance Benchmark ==="
echo "Article count: $ARTICLE_COUNT"
echo ""

# Generate test files
echo "Generating test data..."

generate_articles() {
    local count=$1
    local offset=${2:-0}
    local change_pct=${3:-0}  # Percentage of articles to modify

    for ((i = 1; i <= count; i++)); do
        pmid=$((offset + i))
        title="Article Title Number $pmid with some additional text to make it realistic"
        authors='["Smith A","Jones B","Brown C"]'
        journal="Journal of Testing"
        year="2024"
        abstract="This is the abstract for article $pmid. It contains multiple sentences to simulate real abstract length. The research presents findings that are significant for the field."

        # Randomly modify some articles based on change_pct
        if [[ $change_pct -gt 0 ]] && (( RANDOM % 100 < change_pct )); then
            title="$title (Updated)"
        fi

        echo "{\"pmid\":\"$pmid\",\"title\":\"$title\",\"authors\":$authors,\"journal\":\"$journal\",\"year\":\"$year\",\"abstract\":\"$abstract\"}"
    done
}

# Generate OLD file (all articles)
echo "  Generating OLD file ($ARTICLE_COUNT articles)..."
generate_articles "$ARTICLE_COUNT" 0 0 > "$TMPDIR/old.jsonl"

# Generate NEW file with:
# - 95% unchanged
# - 2% removed (not included)
# - 2% changed (modified title)
# - 1% added (new PMIDs)
echo "  Generating NEW file (with ~5% differences)..."
REMOVED_COUNT=$((ARTICLE_COUNT * 2 / 100))
ADDED_COUNT=$((ARTICLE_COUNT * 1 / 100))
KEEP_COUNT=$((ARTICLE_COUNT - REMOVED_COUNT))
# Note: ~2% of kept articles are randomly modified by awk below

# Copy most articles, skip some (removed), modify some (changed)
head -n "$KEEP_COUNT" "$TMPDIR/old.jsonl" | \
    awk -v change_pct=2 'BEGIN{srand()} {
        if (rand() * 100 < change_pct) {
            gsub(/"title":"[^"]*"/, "\"title\":\"Modified Article Title\"")
        }
        print
    }' > "$TMPDIR/new.jsonl"

# Add new articles at the end
generate_articles "$ADDED_COUNT" "$((ARTICLE_COUNT + 1000))" 0 >> "$TMPDIR/new.jsonl"

OLD_SIZE=$(wc -l < "$TMPDIR/old.jsonl")
NEW_SIZE=$(wc -l < "$TMPDIR/new.jsonl")
echo "  OLD: $OLD_SIZE articles"
echo "  NEW: $NEW_SIZE articles"
echo ""

# Run benchmark
echo "Running pm-diff benchmark..."
echo ""

# Test 1: Summary format (default)
echo "Test 1: Summary format"
START=$(date +%s.%N)
$PM_DIFF "$TMPDIR/old.jsonl" "$TMPDIR/new.jsonl" > "$TMPDIR/result_summary.txt" 2>&1 || true
END=$(date +%s.%N)
DURATION=$(echo "$END - $START" | bc)
echo "  Duration: ${DURATION}s"
echo "  Output:"
sed 's/^/    /' "$TMPDIR/result_summary.txt"
echo ""

# Test 2: --format added (PMID list)
echo "Test 2: --format added"
START=$(date +%s.%N)
$PM_DIFF --format added "$TMPDIR/old.jsonl" "$TMPDIR/new.jsonl" > "$TMPDIR/result_added.txt" 2>&1 || true
END=$(date +%s.%N)
DURATION=$(echo "$END - $START" | bc)
ADDED_RESULT=$(wc -l < "$TMPDIR/result_added.txt")
echo "  Duration: ${DURATION}s"
echo "  Added PMIDs: $ADDED_RESULT"
echo ""

# Test 3: --quiet (exit code only)
echo "Test 3: --quiet mode"
START=$(date +%s.%N)
$PM_DIFF --quiet "$TMPDIR/old.jsonl" "$TMPDIR/new.jsonl" 2>&1 || true
END=$(date +%s.%N)
DURATION=$(echo "$END - $START" | bc)
echo "  Duration: ${DURATION}s"
echo ""

# Test 4: Identical files (best case)
echo "Test 4: Identical files comparison"
START=$(date +%s.%N)
$PM_DIFF --quiet "$TMPDIR/old.jsonl" "$TMPDIR/old.jsonl" 2>&1 || true
END=$(date +%s.%N)
DURATION=$(echo "$END - $START" | bc)
echo "  Duration: ${DURATION}s"
echo ""

# Memory usage (if /usr/bin/time is available)
if command -v /usr/bin/time &> /dev/null; then
    echo "Test 5: Memory usage"
    /usr/bin/time -v "$PM_DIFF" --quiet "$TMPDIR/old.jsonl" "$TMPDIR/new.jsonl" 2>&1 | grep -E "(Maximum resident|Elapsed)" | sed 's/^/  /'
    echo ""
fi

echo "=== Benchmark Complete ==="
