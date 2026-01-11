#!/bin/bash
# Read the last message from a specific role in the handoff file
# Usage: ./read_last.sh ROLE

set -e

role=$1
file="${HANDOFF_FILE:-.claude/handoff.md}"

if [ -z "$role" ]; then
  echo "Error: role is required" >&2
  echo "Usage: $0 ROLE" >&2
  exit 1
fi

if [ ! -f "$file" ]; then
  echo "No handoff file found at $file" >&2
  exit 0
fi

awk -v role="<<<${role}>>>" '
  $0 == role { capture=1; content=""; next }
  $0 == "<<<END>>>" && capture { capture=0; last=content; next }
  capture { content = content $0 "\n" }
  END { printf "%s", last }
' "$file"
