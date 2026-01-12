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

# =============================================================================
# Phase 2: Default Installation
# =============================================================================

@test "pm-skill creates .claude/skills/using-pm-tools/" {
    # Given
    cd "$TEST_DIR"

    # When
    run "$BIN_DIR/pm-skill"

    # Then
    [ "$status" -eq 0 ]
    [ -d ".claude/skills/using-pm-tools" ]
}

@test "pm-skill creates SKILL.md" {
    # Given
    cd "$TEST_DIR"

    # When
    run "$BIN_DIR/pm-skill"

    # Then
    [ "$status" -eq 0 ]
    [ -f ".claude/skills/using-pm-tools/SKILL.md" ]
}

@test "SKILL.md has correct frontmatter" {
    # Given
    cd "$TEST_DIR"
    "$BIN_DIR/pm-skill"

    # When
    local content
    content=$(cat ".claude/skills/using-pm-tools/SKILL.md")

    # Then
    [[ "$content" == *"name: using-pm-tools"* ]]
    [[ "$content" == *"description:"* ]]
}

@test "SKILL.md contains pm-tools documentation" {
    # Given
    cd "$TEST_DIR"
    "$BIN_DIR/pm-skill"

    # When
    local content
    content=$(cat ".claude/skills/using-pm-tools/SKILL.md")

    # Then
    [[ "$content" == *"pm-search"* ]]
    [[ "$content" == *"pm-fetch"* ]]
    [[ "$content" == *"pm-parse"* ]]
}

@test "pm-skill prints success message" {
    # Given
    cd "$TEST_DIR"

    # When
    run "$BIN_DIR/pm-skill"

    # Then
    [ "$status" -eq 0 ]
    [[ "$output" == *"Created:"* ]] || [[ "$output" == *".claude/skills/using-pm-tools"* ]]
}

# =============================================================================
# Phase 3: Conflict Handling
# =============================================================================

@test "pm-skill fails if skill exists" {
    # Given
    cd "$TEST_DIR"
    "$BIN_DIR/pm-skill"  # First install

    # When
    run "$BIN_DIR/pm-skill"  # Second install

    # Then
    [ "$status" -eq 1 ]
    [[ "$output" == *"already exists"* ]]
}

@test "pm-skill --force overwrites existing" {
    # Given
    cd "$TEST_DIR"
    "$BIN_DIR/pm-skill"
    echo "modified" >> ".claude/skills/using-pm-tools/SKILL.md"

    # When
    run "$BIN_DIR/pm-skill" --force

    # Then
    [ "$status" -eq 0 ]
    [[ "$output" == *"Overwritten:"* ]]
    # Verify content is restored (no "modified" at end)
    local content
    content=$(cat ".claude/skills/using-pm-tools/SKILL.md")
    [[ "$content" != *"modified"* ]]
}

@test "pm-skill --force creates if not exists" {
    # Given
    cd "$TEST_DIR"

    # When
    run "$BIN_DIR/pm-skill" --force

    # Then
    [ "$status" -eq 0 ]
    [ -f ".claude/skills/using-pm-tools/SKILL.md" ]
}

# =============================================================================
# Phase 4: Global Installation
# =============================================================================

@test "pm-skill --global creates in ~/.claude/skills/" {
    # Given
    export HOME="$TEST_DIR"

    # When
    run "$BIN_DIR/pm-skill" --global

    # Then
    [ "$status" -eq 0 ]
    [ -f "$TEST_DIR/.claude/skills/using-pm-tools/SKILL.md" ]
}

@test "pm-skill --global fails if exists" {
    # Given
    export HOME="$TEST_DIR"
    "$BIN_DIR/pm-skill" --global  # First install

    # When
    run "$BIN_DIR/pm-skill" --global  # Second install

    # Then
    [ "$status" -eq 1 ]
    [[ "$output" == *"already exists"* ]]
}

@test "pm-skill --global --force overwrites" {
    # Given
    export HOME="$TEST_DIR"
    "$BIN_DIR/pm-skill" --global
    echo "modified" >> "$TEST_DIR/.claude/skills/using-pm-tools/SKILL.md"

    # When
    run "$BIN_DIR/pm-skill" --global --force

    # Then
    [ "$status" -eq 0 ]
    [[ "$output" == *"Overwritten:"* ]]
}

# =============================================================================
# Phase 5: Edge Cases
# =============================================================================

@test "pm-skill rejects unknown options" {
    # Given
    cd "$TEST_DIR"

    # When
    run "$BIN_DIR/pm-skill" --unknown

    # Then
    [ "$status" -eq 1 ]
    [[ "$output" == *"Unknown option"* ]] || [[ "$output" == *"unknown"* ]]
}

@test "pm-skill works when .claude/ exists but skills/ doesn't" {
    # Given
    cd "$TEST_DIR"
    mkdir -p ".claude"

    # When
    run "$BIN_DIR/pm-skill"

    # Then
    [ "$status" -eq 0 ]
    [ -f ".claude/skills/using-pm-tools/SKILL.md" ]
}

@test "pm-skill works in any directory (creates .claude/)" {
    # Given
    cd "$TEST_DIR"
    # TEST_DIR is a fresh temp directory with no .claude/

    # When
    run "$BIN_DIR/pm-skill"

    # Then
    [ "$status" -eq 0 ]
    [ -d ".claude" ]
    [ -f ".claude/skills/using-pm-tools/SKILL.md" ]
}
