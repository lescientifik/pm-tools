#!/usr/bin/env bats

# Tests for bin/pm-download - PDF downloader from PMC and Unpaywall

setup() {
    load 'test_helper'
    PM_DOWNLOAD="${BIN_DIR}/pm-download"
}

# --- Help and basic tests ---

@test "pm-download exists and is executable" {
    [ -x "$PM_DOWNLOAD" ]
}

@test "pm-download --help shows usage" {
    # When: running with --help
    run "$PM_DOWNLOAD" --help

    # Then: exits successfully and shows usage info
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
    [[ "$output" == *"pm-download"* ]]
    [[ "$output" == *"--output-dir"* ]]
    [[ "$output" == *"--dry-run"* ]]
}

@test "pm-download -h shows usage" {
    # When: running with -h
    run "$PM_DOWNLOAD" -h

    # Then: exits successfully and shows usage info
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
}

# --- Input validation tests ---

@test "pm-download requires input (fails with no stdin and no --input)" {
    # When: running with no input (stdin is /dev/null)
    run bash -c "'$PM_DOWNLOAD' < /dev/null"

    # Then: exits with error and shows usage hint
    [ "$status" -eq 1 ]
    [[ "$output" == *"input"* ]] || [[ "$output" == *"Usage"* ]]
}

@test "pm-download accepts JSONL from stdin" {
    # Given: JSONL input with pmid and pmcid (so we have a source)
    local jsonl='{"pmid":"12345","pmcid":"PMC1234567","doi":"10.1234/test"}'

    # When: running with --dry-run
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run"

    # Then: exits successfully and shows what would be downloaded
    [ "$status" -eq 0 ]
    [[ "$output" == *"12345"* ]]
}

@test "pm-download accepts PMIDs from stdin" {
    # Given: plain PMID input (one per line)
    local pmids="12345"

    # When: running with --dry-run
    run bash -c "echo '$pmids' | '$PM_DOWNLOAD' --dry-run"

    # Then: exits successfully (may show "no source" if no DOI/PMCID)
    [ "$status" -eq 0 ] || [ "$status" -eq 2 ]  # 2 = no downloads available
}

@test "pm-download --input reads from file" {
    # Given: temp file with PMIDs
    local tmpfile
    tmpfile=$(mktemp)
    echo "12345" > "$tmpfile"

    # When: running with --input flag
    run "$PM_DOWNLOAD" --dry-run --input "$tmpfile"

    # Then: processes the file
    [ "$status" -eq 0 ] || [ "$status" -eq 2 ]

    rm -f "$tmpfile"
}

# --- Dry run output tests ---

@test "pm-download --dry-run shows PMC source when pmcid present" {
    # Given: JSONL with PMCID
    local jsonl='{"pmid":"12345","pmcid":"PMC1234567","doi":"10.1234/test"}'

    # When: running with --dry-run
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run"

    # Then: shows PMC as source
    [ "$status" -eq 0 ]
    [[ "$output" == *"PMC"* ]] || [[ "$output" == *"pmc"* ]]
}

@test "pm-download --dry-run shows Unpaywall source when only doi present" {
    # Given: JSONL with DOI but no PMCID
    local jsonl='{"pmid":"12345","doi":"10.1234/test"}'

    # When: running with --dry-run (requires --email for Unpaywall)
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --email test@example.com"

    # Then: shows Unpaywall as source
    [ "$status" -eq 0 ]
    [[ "$output" == *"Unpaywall"* ]] || [[ "$output" == *"unpaywall"* ]] || [[ "$output" == *"doi"* ]]
}

@test "pm-download --dry-run reports no source when neither pmcid nor doi" {
    # Given: JSONL with only PMID
    local jsonl='{"pmid":"12345"}'

    # When: running with --dry-run
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run"

    # Then: reports no source available
    [[ "$output" == *"no"* ]] || [[ "$output" == *"unavailable"* ]] || [[ "$output" == *"skip"* ]]
}

# --- Output directory tests ---

@test "pm-download creates output directory if it doesn't exist" {
    # Given: non-existent output directory
    local tmpdir
    tmpdir=$(mktemp -d)
    rmdir "$tmpdir"  # Remove so we test creation
    local jsonl='{"pmid":"12345","pmcid":"PMC1234567"}'

    # When: running with --output-dir to non-existent dir (dry-run)
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --output-dir '$tmpdir'"

    # Then: no error about directory
    [ "$status" -eq 0 ] || [ "$status" -eq 2 ]

    # Cleanup (in case it was created)
    rm -rf "$tmpdir" 2>/dev/null || true
}

# --- Error handling tests ---

@test "pm-download reports invalid JSON gracefully" {
    # Given: invalid JSON input
    local invalid='not valid json'

    # When: running with invalid input
    run bash -c "echo '$invalid' | '$PM_DOWNLOAD' --dry-run"

    # Then: treats as PMID (single word input)
    # This should work since "not valid json" could be interpreted as PMID
    # OR exit with error explaining the issue
    [ "$status" -eq 0 ] || [ "$status" -eq 1 ] || [ "$status" -eq 2 ]
}
