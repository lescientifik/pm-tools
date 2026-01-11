#!/bin/bash
# dtd-to-xpath.sh - Extract element names from a PubMed DTD file
#
# Usage: dtd-to-xpath.sh <dtd_file>
# Output: One element name per line on stdout

set -euo pipefail

# Check argument
if [ $# -lt 1 ]; then
    echo "Usage: $0 <dtd_file>" >&2
    exit 1
fi

DTD_FILE="$1"

# Verify file exists
if [ ! -f "$DTD_FILE" ]; then
    echo "Error: DTD file not found: $DTD_FILE" >&2
    exit 1
fi

# Extract element names from <!ELEMENT declarations
# DTD format: <!ELEMENT ElementName (content-model)>
grep -oE '<!ELEMENT[[:space:]]+[A-Za-z][A-Za-z0-9:_-]*' "$DTD_FILE" \
    | sed 's/<!ELEMENT[[:space:]]*//' \
    | sort -u
