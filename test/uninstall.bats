#!/usr/bin/env bats
# Tests for uninstall.sh - pm-tools uninstaller

setup() {
    TEST_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
    PROJECT_DIR="$(dirname "$TEST_DIR")"
    TEMP_DIR="$(mktemp -d)"
}

teardown() {
    rm -rf "$TEMP_DIR"
}

# =============================================================================
# Basics
# =============================================================================

@test "uninstall.sh exists and is executable" {
    [[ -x "$PROJECT_DIR/uninstall.sh" ]]
}

@test "uninstall.sh --help shows usage" {
    run "$PROJECT_DIR/uninstall.sh" --help
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"Usage:"* ]]
    [[ "$output" == *"--prefix"* ]]
}

@test "uninstall.sh -h is alias for --help" {
    run "$PROJECT_DIR/uninstall.sh" -h
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"Usage:"* ]]
}

# =============================================================================
# Uninstallation
# =============================================================================

@test "uninstall.sh removes all installed files" {
    # Install first
    "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path

    # Verify installation exists
    [[ -x "$TEMP_DIR/bin/pm-search" ]]

    # Uninstall
    run "$PROJECT_DIR/uninstall.sh" --prefix "$TEMP_DIR"
    [[ "$status" -eq 0 ]]

    # Verify removal
    [[ ! -f "$TEMP_DIR/bin/pm-search" ]]
    [[ ! -f "$TEMP_DIR/bin/pm-fetch" ]]
    [[ ! -f "$TEMP_DIR/bin/pm-parse" ]]
    [[ ! -d "$TEMP_DIR/lib/pm-tools" ]]
}

@test "uninstall.sh shows what was removed" {
    # Install first
    "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path

    # Uninstall
    run "$PROJECT_DIR/uninstall.sh" --prefix "$TEMP_DIR"
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"pm-search"* ]]
    [[ "$output" == *"pm-common.sh"* ]] || [[ "$output" == *"pm-tools"* ]]
}

@test "uninstall.sh handles missing installation gracefully" {
    # Don't install, just try to uninstall
    run "$PROJECT_DIR/uninstall.sh" --prefix "$TEMP_DIR"
    # Should not fail hard, just report nothing to remove
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"not found"* ]] || [[ "$output" == *"Nothing"* ]] || [[ "$output" == *"already"* ]]
}

@test "uninstall.sh preserves other files in bin/" {
    # Install pm-tools
    "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path

    # Add another file to bin/
    echo "#!/bin/bash" > "$TEMP_DIR/bin/my-other-script"

    # Uninstall
    "$PROJECT_DIR/uninstall.sh" --prefix "$TEMP_DIR"

    # Other file should remain
    [[ -f "$TEMP_DIR/bin/my-other-script" ]]
}
