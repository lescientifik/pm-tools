#!/usr/bin/env bash
# pm-common.sh - Shared utility functions for pm-* tools

# Print error message to stderr and exit with code 1
# Usage: die "error message"
die() {
    echo "$*" >&2
    exit 1
}

# Print message to stderr only if VERBOSE is set to 1
# Usage: VERBOSE=1 log_verbose "debug info"
log_verbose() {
    if [[ "${VERBOSE:-}" == "1" ]]; then
        echo "$*" >&2
    fi
}

# Check that required commands are available
# Usage: require_commands curl jq xml2
require_commands() {
    local missing=()
    for cmd in "$@"; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing required commands: ${missing[*]}. Install with: apt install ${missing[*]}"
    fi
}
