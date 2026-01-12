#!/usr/bin/env bats
# Tests for pm-skill - Claude Code skill installer

setup() {
    load test_helper
    TEST_DIR="$(mktemp -d)"
}

teardown() {
    rm -rf "$TEST_DIR"
}

# =============================================================================
# Phase 1: Skeleton and Help
# =============================================================================

@test "pm-skill exists and is executable" {
    # Given
    local script="$BIN_DIR/pm-skill"

    # Then
    [ -f "$script" ]
    [ -x "$script" ]
}

@test "pm-skill --help shows usage" {
    # When
    run "$BIN_DIR/pm-skill" --help

    # Then
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage:"* ]]
    [[ "$output" == *"--global"* ]]
    [[ "$output" == *"--force"* ]]
}

@test "pm-skill -h is alias for --help" {
    # When
    run "$BIN_DIR/pm-skill" -h

    # Then
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage:"* ]]
}
