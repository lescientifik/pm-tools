#!/bin/bash
# Append a message to the handoff file with role markers
# Usage: cat << 'EOF' | ./write_message.sh ROLE
#        message content
#        EOF
# Or: echo "message" | ./write_message.sh ROLE

set -e

role=$1
file="${HANDOFF_FILE:-.claude/handoff.md}"

if [ -z "$role" ]; then
  echo "Error: role is required" >&2
  echo "Usage: echo 'message' | $0 ROLE" >&2
  exit 1
fi

# Create directory if needed
mkdir -p "$(dirname "$file")"

# Append message with markers
{
  echo "<<<${role}>>>"
  cat
  echo ""
  echo "<<<END>>>"
} >> "$file"
