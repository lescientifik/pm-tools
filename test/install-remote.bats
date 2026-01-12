#!/usr/bin/env bats
# Tests for install-remote.sh - curl-installable pm-tools installer

setup() {
    # Get the directory containing this test file
    TEST_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
    PROJECT_DIR="$(dirname "$TEST_DIR")"

    # Create temp directory for each test
    TEMP_DIR="$(mktemp -d)"

    # Source test helpers if available
    if [[ -f "$TEST_DIR/test_helper.bash" ]]; then
        source "$TEST_DIR/test_helper.bash"
    fi
}

teardown() {
    # Clean up temp directory
    rm -rf "$TEMP_DIR"
}

# =============================================================================
# Phase 1: Script basics
# =============================================================================

@test "install-remote.sh exists and is executable" {
    [[ -x "$PROJECT_DIR/install-remote.sh" ]]
}

@test "install-remote.sh --help shows usage" {
    run "$PROJECT_DIR/install-remote.sh" --help
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"Usage:"* ]]
    [[ "$output" == *"--prefix"* ]]
}

@test "install-remote.sh -h is alias for --help" {
    run "$PROJECT_DIR/install-remote.sh" -h
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"Usage:"* ]]
}

@test "install-remote.sh --version shows version number" {
    run "$PROJECT_DIR/install-remote.sh" --version
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

@test "install-remote.sh rejects unknown options" {
    run "$PROJECT_DIR/install-remote.sh" --unknown-option
    [[ "$status" -eq 1 ]]
    [[ "$output" == *"Unknown"* ]]
}

# =============================================================================
# Phase 2: Pre-flight checks
# =============================================================================

@test "install-remote.sh --check-only runs checks without installing" {
    run "$PROJECT_DIR/install-remote.sh" --check-only --prefix "$TEMP_DIR"
    # Should pass checks (we have bash, curl, etc.)
    [[ "$status" -eq 0 ]]
    # Should NOT create any files
    [[ ! -d "$TEMP_DIR/bin" ]]
}

@test "install-remote.sh fails if prefix not writable" {
    run "$PROJECT_DIR/install-remote.sh" --check-only --prefix "/root/nonexistent"
    [[ "$status" -eq 1 ]]
    [[ "$output" == *"permission"* ]] || [[ "$output" == *"Cannot"* ]] || [[ "$output" == *"write"* ]]
}

# =============================================================================
# Phase 3: Dependency checking
# =============================================================================

@test "install-remote.sh --check-deps shows dependency status" {
    run "$PROJECT_DIR/install-remote.sh" --check-deps
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"curl"* ]]
    [[ "$output" == *"xml2"* ]]
    [[ "$output" == *"jq"* ]]
}

@test "install-remote.sh --check-deps shows mawk as optional" {
    run "$PROJECT_DIR/install-remote.sh" --check-deps
    [[ "$output" == *"mawk"* ]]
    [[ "$output" == *"optional"* ]] || [[ "$output" == *"Optional"* ]]
}

# =============================================================================
# Phase 4: Offline installation (for testing)
# =============================================================================

@test "install-remote.sh --offline installs from local files" {
    run "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path
    [[ "$status" -eq 0 ]]

    # Check all commands installed
    for cmd in pm-search pm-fetch pm-parse pm-filter pm-show pm-download pm-diff pm-quick pm-skill; do
        [[ -x "$TEMP_DIR/bin/$cmd" ]]
    done

    # Check library installed
    [[ -f "$TEMP_DIR/lib/pm-tools/pm-common.sh" ]]
}

@test "install-remote.sh rewrites library path correctly" {
    "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path

    # Check that pm-search sources the correct library path
    grep -q "source \"$TEMP_DIR/lib/pm-tools/pm-common.sh\"" "$TEMP_DIR/bin/pm-search"
}

@test "install-remote.sh installed commands work" {
    "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path

    # Test pm-parse --help works
    run "$TEMP_DIR/bin/pm-parse" --help
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"JSONL"* ]]
}

@test "install-remote.sh overwrites existing installation" {
    # First install
    "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path

    # Modify a file
    echo "# modified" >> "$TEMP_DIR/bin/pm-search"

    # Second install should overwrite
    run "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path
    [[ "$status" -eq 0 ]]

    # File should not have our modification
    ! grep -q "# modified" "$TEMP_DIR/bin/pm-search"
}

@test "install-remote.sh shows success message" {
    run "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"success"* ]] || [[ "$output" == *"Success"* ]] || [[ "$output" == *"complete"* ]] || [[ "$output" == *"Complete"* ]]
}

# =============================================================================
# Phase 5: PATH handling
# =============================================================================

@test "install-remote.sh shows PATH instructions when bin not in PATH" {
    # Use a prefix that's definitely not in PATH
    run "$PROJECT_DIR/install-remote.sh" --offline --prefix "$TEMP_DIR" --no-modify-path
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"PATH"* ]]
    [[ "$output" == *"$TEMP_DIR/bin"* ]]
}

# =============================================================================
# Phase 6: Edge cases
# =============================================================================

@test "install-remote.sh handles spaces in prefix path" {
    local space_dir="$TEMP_DIR/my folder"
    mkdir -p "$space_dir"

    run "$PROJECT_DIR/install-remote.sh" --offline --prefix "$space_dir" --no-modify-path
    [[ "$status" -eq 0 ]]
    [[ -x "$space_dir/bin/pm-search" ]]
}

@test "install-remote.sh creates prefix directories if needed" {
    local nested="$TEMP_DIR/a/b/c"

    run "$PROJECT_DIR/install-remote.sh" --offline --prefix "$nested" --no-modify-path
    [[ "$status" -eq 0 ]]
    [[ -d "$nested/bin" ]]
    [[ -d "$nested/lib/pm-tools" ]]
}
