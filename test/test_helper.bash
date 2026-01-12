# test_helper.bash - Common utilities for bats tests

# Project directories
export PROJECT_DIR="${BATS_TEST_DIRNAME}/.."
export BIN_DIR="${PROJECT_DIR}/bin"
export LIB_DIR="${PROJECT_DIR}/lib"
export FIXTURES_DIR="${PROJECT_DIR}/fixtures"

# Paths to executables
export PM_SEARCH="${BIN_DIR}/pm-search"
export PM_FETCH="${BIN_DIR}/pm-fetch"
export PM_PARSE="${BIN_DIR}/pm-parse"
export PM_FILTER="${BIN_DIR}/pm-filter"
export PM_DIFF="${BIN_DIR}/pm-diff"
export PM_QUICK="${BIN_DIR}/pm-quick"

# Path to common library
export PM_COMMON="${LIB_DIR}/pm-common.sh"

# Load a fixture file and echo its contents
# Usage: load_fixture "edge-cases/no-doi.xml"
load_fixture() {
    local fixture_path="${FIXTURES_DIR}/${1}"
    if [[ -f "$fixture_path" ]]; then
        cat "$fixture_path"
    else
        echo "Fixture not found: $fixture_path" >&2
        return 1
    fi
}

# Load expected output for comparison
# Usage: load_expected "sample.jsonl"
load_expected() {
    local expected_path="${FIXTURES_DIR}/expected/${1}"
    if [[ -f "$expected_path" ]]; then
        cat "$expected_path"
    else
        echo "Expected file not found: $expected_path" >&2
        return 1
    fi
}
