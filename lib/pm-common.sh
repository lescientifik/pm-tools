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

# Read PMIDs from stdin into array variable
# Usage: read_pmids_to_array array_name
# Empty lines are skipped
read_pmids_to_array() {
    local -n _arr=$1
    _arr=()
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" ]] && continue
        _arr+=("$line")
    done
}

# Process items in batches with rate limiting
# Usage: process_batches callback batch_size delay item1 item2 ...
# callback receives comma-separated list of items for each batch
process_batches() {
    local callback=$1 batch_size=$2 delay=$3
    shift 3
    local items=("$@")

    [[ ${#items[@]} -eq 0 ]] && return 0

    local batch_num=0
    for ((i = 0; i < ${#items[@]}; i += batch_size)); do
        if ((batch_num > 0)) && [[ "$delay" != "0" ]]; then sleep "$delay"; fi
        ((++batch_num))

        # Build comma-separated list
        local batch_ids=""
        for ((j = i; j < i + batch_size && j < ${#items[@]}; j++)); do
            [[ -n "$batch_ids" ]] && batch_ids+=","
            batch_ids+="${items[j]}"
        done

        "$callback" "$batch_ids"
    done
}
