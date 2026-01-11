#!/bin/bash
# benchmark-parser.sh - Benchmark a parser's performance on XML files
#
# Usage: benchmark-parser.sh <parser_command> <xml_file> [article_count]
# Output: Timing stats (total time, articles/second)
#
# The parser command should read from stdin and produce JSONL output.
# If article_count is not specified, it will count output lines.

set -euo pipefail

# Check arguments
if [ $# -lt 2 ]; then
    echo "Usage: $0 <parser_command> <xml_file> [article_count]" >&2
    echo "" >&2
    echo "Examples:" >&2
    echo "  $0 ./bin/pm-parse data/sample.xml" >&2
    echo "  $0 'cat -' data/sample.xml 1000" >&2
    exit 1
fi

PARSER="$1"
XML_FILE="$2"
ARTICLE_COUNT="${3:-}"

# Verify file exists
if [ ! -f "$XML_FILE" ]; then
    echo "Error: File not found: $XML_FILE" >&2
    exit 1
fi

# Determine if file is gzipped
if [[ "$XML_FILE" == *.gz ]]; then
    CAT_CMD="zcat"
else
    CAT_CMD="cat"
fi

# Create temp file for output
TMP_OUTPUT=$(mktemp)
trap 'rm -f "$TMP_OUTPUT"' EXIT

echo "Benchmarking: $PARSER" >&2
echo "Input file: $XML_FILE" >&2
echo "" >&2

# Time the execution
START_TIME=$(date +%s.%N)

$CAT_CMD "$XML_FILE" | $PARSER > "$TMP_OUTPUT" 2>/dev/null || true

END_TIME=$(date +%s.%N)

# Calculate elapsed time
ELAPSED=$(echo "$END_TIME - $START_TIME" | bc)

# Count articles if not specified
if [ -z "$ARTICLE_COUNT" ]; then
    ARTICLE_COUNT=$(wc -l < "$TMP_OUTPUT")
fi

# Calculate articles per second
if [ "$(echo "$ELAPSED > 0" | bc)" -eq 1 ]; then
    RATE=$(echo "scale=2; $ARTICLE_COUNT / $ELAPSED" | bc)
else
    RATE="N/A"
fi

# Output results
echo "=== Benchmark Results ==="
echo "Total time: ${ELAPSED} sec"
echo "Articles processed: $ARTICLE_COUNT"
echo "Rate: ${RATE} articles/sec"

# Memory info (if available)
if command -v free &> /dev/null; then
    echo ""
    echo "Memory:"
    free -h | grep "Mem:" | awk '{print "  Total: " $2 ", Used: " $3 ", Available: " $7}'
fi
