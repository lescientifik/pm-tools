#!/usr/bin/env bats

# Tests for lib/pm-common.sh utility functions

setup() {
    # Load test helper
    load 'test_helper'
}

@test "die prints message to stderr and exits 1" {
    # Given: a script that sources pm-common and calls die
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
die "something went wrong"
EOF
    chmod +x "$test_script"

    # When: running the script
    run bash -c "PM_COMMON='$PM_COMMON' '$test_script'"

    # Then: exit code is 1 and message is on stderr
    [ "$status" -eq 1 ]
    [[ "$output" == *"something went wrong"* ]]

    rm -f "$test_script"
}

@test "log_verbose prints to stderr when VERBOSE=1" {
    # Given: VERBOSE is set
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
VERBOSE=1
log_verbose "debug message"
EOF
    chmod +x "$test_script"

    # When: running the script
    run bash -c "PM_COMMON='$PM_COMMON' '$test_script'" 2>&1

    # Then: message appears on stderr
    [[ "$output" == *"debug message"* ]]

    rm -f "$test_script"
}

@test "log_verbose is silent when VERBOSE is unset" {
    # Given: VERBOSE is not set
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
unset VERBOSE
log_verbose "debug message"
echo "stdout only"
EOF
    chmod +x "$test_script"

    # When: running the script
    run bash -c "PM_COMMON='$PM_COMMON' '$test_script'"

    # Then: only stdout appears, no debug message
    [ "$status" -eq 0 ]
    [[ "$output" == "stdout only" ]]

    rm -f "$test_script"
}

# =============================================================================
# Phase 0.1: read_pmids_to_array() tests
# =============================================================================

@test "read_pmids_to_array reads PMIDs from stdin" {
    # Given: a script that reads 3 PMIDs
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
read_pmids_to_array arr
echo "${#arr[@]}:${arr[0]}:${arr[2]}"
EOF
    chmod +x "$test_script"

    # When: piping 3 PMIDs
    run bash -c "echo -e '123\n456\n789' | PM_COMMON='$PM_COMMON' '$test_script'"

    # Then: array has 3 elements with correct values
    [ "$status" -eq 0 ]
    [ "$output" = "3:123:789" ]

    rm -f "$test_script"
}

@test "read_pmids_to_array skips empty lines" {
    # Given: a script that reads PMIDs with empty lines
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
read_pmids_to_array arr
echo "${#arr[@]}"
EOF
    chmod +x "$test_script"

    # When: piping PMIDs with empty line in middle
    run bash -c "echo -e '123\n\n456' | PM_COMMON='$PM_COMMON' '$test_script'"

    # Then: only 2 elements (empty line skipped)
    [ "$status" -eq 0 ]
    [ "$output" = "2" ]

    rm -f "$test_script"
}

@test "read_pmids_to_array handles empty input" {
    # Given: a script that reads from empty input
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
read_pmids_to_array arr
echo "${#arr[@]}"
EOF
    chmod +x "$test_script"

    # When: piping empty string
    run bash -c "echo '' | PM_COMMON='$PM_COMMON' '$test_script'"

    # Then: array is empty
    [ "$status" -eq 0 ]
    [ "$output" = "0" ]

    rm -f "$test_script"
}

# =============================================================================
# Phase 0.2: process_batches() tests
# =============================================================================

@test "process_batches calls callback for each batch" {
    # Given: a script that processes 5 items in batches of 2
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
mock_callback() { echo "BATCH:$1"; }
process_batches mock_callback 2 0 a b c d e
EOF
    chmod +x "$test_script"

    # When: running the script
    run bash -c "PM_COMMON='$PM_COMMON' '$test_script'"

    # Then: 3 batches are processed
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | wc -l)" -eq 3 ]
    [ "$(echo "$output" | head -1)" = "BATCH:a,b" ]
    [ "$(echo "$output" | tail -1)" = "BATCH:e" ]

    rm -f "$test_script"
}

@test "process_batches handles single item" {
    # Given: a script that processes 1 item
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
mock_callback() { echo "GOT:$1"; }
process_batches mock_callback 100 0 single
EOF
    chmod +x "$test_script"

    # When: running the script
    run bash -c "PM_COMMON='$PM_COMMON' '$test_script'"

    # Then: single item batch
    [ "$status" -eq 0 ]
    [ "$output" = "GOT:single" ]

    rm -f "$test_script"
}

@test "process_batches handles empty input" {
    # Given: a script that processes no items
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
mock_callback() { echo "CALLED"; }
process_batches mock_callback 100 0
EOF
    chmod +x "$test_script"

    # When: running the script
    run bash -c "PM_COMMON='$PM_COMMON' '$test_script'"

    # Then: no output (callback never called)
    [ "$status" -eq 0 ]
    [ -z "$output" ]

    rm -f "$test_script"
}

@test "process_batches respects batch size" {
    # Given: a script that counts items per batch
    local test_script
    test_script=$(mktemp)
    cat > "$test_script" <<'EOF'
#!/usr/bin/env bash
source "$PM_COMMON"
mock_callback() { echo "$1" | tr ',' '\n' | wc -l; }
process_batches mock_callback 3 0 a b c d e f g h i j
EOF
    chmod +x "$test_script"

    # When: running the script (10 items, batch size 3 = 3,3,3,1)
    run bash -c "PM_COMMON='$PM_COMMON' '$test_script'"

    # Then: first batch has 3 items, last batch has 1 item
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | head -1 | tr -d ' ')" = "3" ]
    [ "$(echo "$output" | tail -1 | tr -d ' ')" = "1" ]

    rm -f "$test_script"
}
