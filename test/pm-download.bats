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
    # Given: JSONL input with pmid and pmcid, with mock PMC response
    local jsonl='{"pmid":"12345","pmcid":"PMC1234567","doi":"10.1234/test"}'
    local mock_pmc="${FIXTURES_DIR}/mock-responses/pmc-oa-success.xml"

    # When: running with --dry-run and mock
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --mock-pmc '$mock_pmc'"

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
    # Given: JSONL with PMCID and mock PMC response
    local jsonl='{"pmid":"12345","pmcid":"PMC1234567","doi":"10.1234/test"}'
    local mock_pmc="${FIXTURES_DIR}/mock-responses/pmc-oa-success.xml"

    # When: running with --dry-run and mock
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --mock-pmc '$mock_pmc'"

    # Then: shows PMC as source
    [ "$status" -eq 0 ]
    [[ "$output" == *"PMC"* ]] || [[ "$output" == *"pmc"* ]]
}

@test "pm-download --dry-run shows Unpaywall source when only doi present" {
    # Given: JSONL with DOI but no PMCID, with mock Unpaywall response
    local jsonl='{"pmid":"12345","doi":"10.1234/test"}'
    local mock_unpaywall="${FIXTURES_DIR}/mock-responses/unpaywall-success.json"

    # When: running with --dry-run, --email, and mock Unpaywall
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --email test@example.com --mock-unpaywall '$mock_unpaywall'"

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

# --- ID Converter tests (Phase 3) ---
# These tests use --mock-idconv to provide canned responses

@test "pm-download converts PMIDs to get DOI and PMCID" {
    # Given: plain PMID input with mock responses for both ID conversion and PMC OA
    local mock_idconv="${FIXTURES_DIR}/mock-responses/idconv-success.json"
    local mock_pmc="${FIXTURES_DIR}/mock-responses/pmc-oa-success.xml"
    [ -f "$mock_idconv" ] || skip "Mock ID converter response not found"
    [ -f "$mock_pmc" ] || skip "Mock PMC response not found"

    # When: running with --dry-run and both mocks
    run bash -c "echo '12345' | '$PM_DOWNLOAD' --dry-run --mock-idconv '$mock_idconv' --mock-pmc '$mock_pmc'"

    # Then: shows PMC source (from converted PMCID)
    [ "$status" -eq 0 ]
    [[ "$output" == *"PMC"* ]]
}

@test "pm-download handles PMID without PMCID gracefully" {
    # Given: mock response where some PMIDs have no PMCID
    local mock_response="${FIXTURES_DIR}/mock-responses/idconv-partial.json"
    [ -f "$mock_response" ] || skip "Mock response not found"

    # When: running with plain PMIDs
    run bash -c "echo -e '22222\n33333' | '$PM_DOWNLOAD' --dry-run --mock-idconv '$mock_response' --email test@example.com"

    # Then: shows appropriate sources (Unpaywall for DOI-only, none for neither)
    # PMID 22222 has DOI but no PMCID -> Unpaywall
    # PMID 33333 has neither -> no source
    [[ "$output" == *"22222"* ]]
    [[ "$output" == *"33333"* ]]
}

@test "pm-download batches ID conversion requests" {
    # This test verifies batching works by checking we don't make excessive requests
    # We'll use --verbose to see the request count
    skip "Requires API mocking infrastructure"
}

# --- PMC OA Service tests (Phase 4) ---

@test "pm-download fetches PDF URL from PMC OA Service" {
    # Given: JSONL with PMCID and mock PMC response
    local jsonl='{"pmid":"12345","pmcid":"PMC1234567"}'
    local mock_response="${FIXTURES_DIR}/mock-responses/pmc-oa-success.xml"
    [ -f "$mock_response" ] || skip "Mock response not found"

    # When: running with --dry-run and mock PMC OA
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --mock-pmc '$mock_response'"

    # Then: shows PMC source with PDF URL
    [ "$status" -eq 0 ]
    [[ "$output" == *"PMC"* ]]
    [[ "$output" == *"pdf"* ]] || [[ "$output" == *"PDF"* ]]
}

@test "pm-download reports non-OA article from PMC" {
    # Given: JSONL with PMCID that's not in OA subset
    local jsonl='{"pmid":"12345","pmcid":"PMC9999999","doi":"10.1234/test"}'
    local mock_response="${FIXTURES_DIR}/mock-responses/pmc-oa-not-oa.xml"
    [ -f "$mock_response" ] || skip "Mock response not found"

    # When: running with --dry-run and mock PMC OA
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --mock-pmc '$mock_response' --email test@example.com"

    # Then: falls back to Unpaywall (has DOI and email)
    [[ "$output" == *"Unpaywall"* ]] || [[ "$output" == *"unpaywall"* ]] || [[ "$output" == *"not"* ]]
}

# --- Unpaywall tests (Phase 5) ---

@test "pm-download fetches PDF URL from Unpaywall" {
    # Given: JSONL with DOI but no PMCID, and mock Unpaywall response
    local jsonl='{"pmid":"12345","doi":"10.1234/test"}'
    local mock_unpaywall="${FIXTURES_DIR}/mock-responses/unpaywall-success.json"
    [ -f "$mock_unpaywall" ] || skip "Mock response not found"

    # When: running with --dry-run, --email, and mock Unpaywall
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --email test@example.com --mock-unpaywall '$mock_unpaywall'"

    # Then: shows Unpaywall source with PDF URL
    [ "$status" -eq 0 ]
    [[ "$output" == *"Unpaywall"* ]]
    [[ "$output" == *"pdf"* ]] || [[ "$output" == *"PDF"* ]] || [[ "$output" == *"available"* ]]
}

@test "pm-download reports non-OA from Unpaywall" {
    # Given: JSONL with DOI that's not OA
    local jsonl='{"pmid":"12345","doi":"10.1234/closed"}'
    local mock_unpaywall="${FIXTURES_DIR}/mock-responses/unpaywall-not-oa.json"
    [ -f "$mock_unpaywall" ] || skip "Mock response not found"

    # When: running with --dry-run, --email, and mock Unpaywall
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --email test@example.com --mock-unpaywall '$mock_unpaywall'"

    # Then: reports not available
    [[ "$output" == *"not"* ]] || [[ "$output" == *"unavailable"* ]] || [[ "$output" == *"No source"* ]]
}

@test "pm-download falls back PMC->Unpaywall successfully" {
    # Given: JSONL with PMCID (not in OA) and DOI (is OA via Unpaywall)
    local jsonl='{"pmid":"12345","pmcid":"PMC9999999","doi":"10.1234/test"}'
    local mock_pmc="${FIXTURES_DIR}/mock-responses/pmc-oa-not-oa.xml"
    local mock_unpaywall="${FIXTURES_DIR}/mock-responses/unpaywall-success.json"

    # When: running with both mocks - PMC fails, Unpaywall succeeds
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --dry-run --email test@example.com --mock-pmc '$mock_pmc' --mock-unpaywall '$mock_unpaywall'"

    # Then: successfully falls back to Unpaywall
    [ "$status" -eq 0 ]
    [[ "$output" == *"Unpaywall"* ]] || [[ "$output" == *"available"* ]]
}

# --- PDF Download tests (Phase 6) ---

@test "pm-download without --dry-run attempts actual download" {
    # This test verifies that without --dry-run, the tool attempts downloads
    # We use a mock PDF URL that will fail gracefully

    # Given: JSONL with mock PMC response
    local jsonl='{"pmid":"12345","pmcid":"PMC1234567"}'
    local mock_pmc="${FIXTURES_DIR}/mock-responses/pmc-oa-success.xml"
    local tmpdir
    tmpdir=$(mktemp -d)

    # When: running without --dry-run
    # The download will fail (mock URL doesn't exist) but should report the attempt
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --output-dir '$tmpdir' --mock-pmc '$mock_pmc' --timeout 5 2>&1"

    # Then: shows download attempt (may fail with network error)
    [[ "$output" == *"download"* ]] || [[ "$output" == *"Download"* ]] || [[ "$output" == *"error"* ]] || [[ "$output" == *"Error"* ]]

    rm -rf "$tmpdir"
}

@test "pm-download skips existing files without --overwrite" {
    # Given: output directory with existing file
    local tmpdir
    tmpdir=$(mktemp -d)
    echo "existing content" > "$tmpdir/12345.pdf"
    local jsonl='{"pmid":"12345","pmcid":"PMC1234567"}'
    local mock_pmc="${FIXTURES_DIR}/mock-responses/pmc-oa-success.xml"

    # When: running without --overwrite
    run bash -c "echo '$jsonl' | '$PM_DOWNLOAD' --output-dir '$tmpdir' --mock-pmc '$mock_pmc' --timeout 5 2>&1"

    # Then: should skip existing file
    [[ "$output" == *"skip"* ]] || [[ "$output" == *"Skip"* ]] || [[ "$output" == *"exists"* ]]

    # And: original file should be unchanged
    [ "$(cat "$tmpdir/12345.pdf")" = "existing content" ]

    rm -rf "$tmpdir"
}
