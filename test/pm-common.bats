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
