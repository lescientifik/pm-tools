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
