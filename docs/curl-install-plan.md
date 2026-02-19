# Implementation Plan: curl-installable pm-tools

A detailed TDD implementation plan for making pm-tools installable via:

```bash
curl -fsSL https://raw.githubusercontent.com/lescientifik/pm-tools/main/install-remote.sh | bash
```

## Overview

### Goal
Enable one-command installation of pm-tools from GitHub without cloning the repository.

### Current State
- `install.sh` exists but requires local clone
- 9 commands: `pm search`, `pm fetch`, `pm parse`, `pm filter`, `pm show`, `pm download`, `pm diff`, `pm quick`, `pm skill`
- 1 library: `lib/pm-common.sh`
- Dependencies: `curl`, `xml2`, `jq`, `grep`, (`mawk` optional)

### Design Principles
1. **Single command install**: No git required, no manual steps
2. **Fail-safe**: Validate dependencies and permissions before changes
3. **Reversible**: Include uninstall option
4. **Non-destructive**: Backup existing installations
5. **Configurable**: Allow custom install prefix
6. **Testable**: All logic testable offline

## Architecture

### Installation Flow

```
User runs: curl -fsSL .../install-remote.sh | bash
                           |
                           v
            +---------------------------+
            |  1. Pre-flight checks     |
            |  - Bash version >= 4.0    |
            |  - curl available         |
            |  - Write permissions      |
            +---------------------------+
                           |
                           v
            +---------------------------+
            |  2. Detect parameters     |
            |  - VERSION (default: main)|
            |  - PREFIX (~/.local)      |
            |  - Interactive mode       |
            +---------------------------+
                           |
                           v
            +---------------------------+
            |  3. Check dependencies    |
            |  - xml2, jq, curl, grep   |
            |  - Warn for mawk (opt)    |
            +---------------------------+
                           |
                           v
            +---------------------------+
            |  4. Download files        |
            |  - Fetch from GitHub raw  |
            |  - Verify content         |
            +---------------------------+
                           |
                           v
            +---------------------------+
            |  5. Install files         |
            |  - Create directories     |
            |  - Rewrite lib paths      |
            |  - Set permissions        |
            +---------------------------+
                           |
                           v
            +---------------------------+
            |  6. Post-install          |
            |  - Verify installation    |
            |  - Show PATH instructions |
            |  - Optional: add to PATH  |
            +---------------------------+
```

### File Structure Changes

```
pubmed_parser/
├── install.sh              # Local installation (keep as-is)
├── install-remote.sh       # NEW: curl-installable script
├── uninstall.sh            # NEW: clean removal script
├── VERSION                 # NEW: version file
├── bin/                    # Commands (unchanged)
├── lib/                    # Library (unchanged)
└── test/
    ├── install-remote.bats # NEW: tests for remote installer
    └── uninstall.bats      # NEW: tests for uninstaller
```

## Data Analysis

### Files to Download

| File | Size (approx) | Critical |
|------|---------------|----------|
| `lib/pm-common.sh` | 1 KB | Yes |
| `bin/pm search` | 3 KB | Yes |
| `bin/pm fetch` | 4 KB | Yes |
| `bin/pm parse` | 15 KB | Yes |
| `bin/pm filter` | 8 KB | Yes |
| `bin/pm show` | 3 KB | Yes |
| `bin/pm download` | 18 KB | Yes |
| `bin/pm diff` | 11 KB | Yes |
| `bin/pm quick` | 3 KB | Yes |
| `bin/pm skill` | 6 KB | Yes |
| **Total** | ~70 KB | |

### Dependency Requirements

| Dependency | Required For | Check Command |
|------------|--------------|---------------|
| `bash` >= 4.0 | Installer + commands | `bash --version` |
| `curl` | HTTP requests | `command -v curl` |
| `xml2` | XML parsing | `command -v xml2` |
| `jq` | JSON processing | `command -v jq` |
| `grep` (GNU) | Pattern matching | `command -v grep` |
| `mawk` (opt) | 2x faster parsing | `command -v mawk` |

### Platform Considerations

| Platform | Package Manager | Install Command |
|----------|-----------------|-----------------|
| Debian/Ubuntu | apt | `sudo apt install xml2 jq curl mawk` |
| macOS | brew | `brew install xml2 jq mawk` |
| Fedora/RHEL | dnf | `sudo dnf install xml2 jq curl mawk` |
| Alpine | apk | `apk add xml2 jq curl mawk` |

## Test Plan

### Phase 1: Unit Tests for install-remote.sh Functions

#### 1.1 Pre-flight checks

```bash
@test "install-remote: fails if bash version < 4.0" {
    # Mock BASH_VERSION to 3.2
    run bash -c 'BASH_VERSION=3.2.0 source ./install-remote.sh --check-only'
    [ "$status" -eq 1 ]
    [[ "$output" == *"Bash 4.0+"* ]]
}

@test "install-remote: fails if curl not available" {
    run env PATH="" bash ./install-remote.sh --check-only
    [ "$status" -eq 1 ]
    [[ "$output" == *"curl"* ]]
}

@test "install-remote: fails if no write permission" {
    run bash ./install-remote.sh --prefix /root/test --check-only
    [ "$status" -eq 1 ]
    [[ "$output" == *"permission"* ]]
}
```

#### 1.2 Dependency checking

```bash
@test "install-remote: warns when xml2 missing" {
    run env PATH="/usr/bin" bash ./install-remote.sh --check-deps
    [[ "$output" == *"xml2"* ]]
    [[ "$output" == *"missing"* ]]
}

@test "install-remote: shows install instructions for missing deps" {
    run env PATH="/usr/bin" bash ./install-remote.sh --check-deps
    [[ "$output" == *"apt install"* ]] || [[ "$output" == *"brew install"* ]]
}

@test "install-remote: optional mawk shows as suggestion not error" {
    run bash ./install-remote.sh --check-deps
    [[ "$output" == *"mawk"* ]] && [[ "$output" == *"optional"* ]]
}
```

#### 1.3 Download verification

```bash
@test "install-remote: validates downloaded file has shebang" {
    # Mock download that returns HTML (404 page)
    run bash -c 'echo "<html>" | validate_script'
    [ "$status" -eq 1 ]
    [[ "$output" == *"invalid"* ]]
}

@test "install-remote: accepts valid shell script" {
    run bash -c 'echo "#!/usr/bin/env bash" | validate_script'
    [ "$status" -eq 0 ]
}
```

#### 1.4 Path rewriting

```bash
@test "install-remote: rewrites lib path correctly" {
    local input='source "${SCRIPT_DIR}/../lib/pm-common.sh"'
    local expected='source "/home/user/.local/lib/pm-tools/pm-common.sh"'
    result=$(echo "$input" | rewrite_lib_path "/home/user/.local/lib/pm-tools")
    [ "$result" == "$expected" ]
}
```

### Phase 2: Integration Tests

#### 2.1 Full installation flow

```bash
@test "install-remote: installs all commands to prefix" {
    local tmpdir=$(mktemp -d)
    trap "rm -rf $tmpdir" EXIT

    run bash ./install-remote.sh --prefix "$tmpdir" --offline-dir ./
    [ "$status" -eq 0 ]

    # Verify all binaries installed
    for cmd in pm search pm fetch pm parse pm filter pm show pm download pm diff pm quick pm skill; do
        [ -x "$tmpdir/bin/$cmd" ]
    done

    # Verify library installed
    [ -f "$tmpdir/lib/pm-tools/pm-common.sh" ]
}

@test "install-remote: installed commands work" {
    local tmpdir=$(mktemp -d)
    trap "rm -rf $tmpdir" EXIT

    bash ./install-remote.sh --prefix "$tmpdir" --offline-dir ./

    # Test a simple command
    run "$tmpdir/bin/pm parse" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"JSONL"* ]]
}

@test "install-remote: backs up existing installation" {
    local tmpdir=$(mktemp -d)
    trap "rm -rf $tmpdir" EXIT

    # Create existing installation
    mkdir -p "$tmpdir/bin"
    echo "old version" > "$tmpdir/bin/pm search"

    bash ./install-remote.sh --prefix "$tmpdir" --offline-dir ./

    # Check backup exists
    [ -f "$tmpdir/bin/pm search.backup" ] || [ -d "$tmpdir/lib/pm-tools.backup" ]
}
```

#### 2.2 Uninstallation

```bash
@test "uninstall: removes all installed files" {
    local tmpdir=$(mktemp -d)
    trap "rm -rf $tmpdir" EXIT

    # Install first
    bash ./install-remote.sh --prefix "$tmpdir" --offline-dir ./

    # Uninstall
    run bash ./uninstall.sh --prefix "$tmpdir"
    [ "$status" -eq 0 ]

    # Verify removal
    [ ! -f "$tmpdir/bin/pm search" ]
    [ ! -d "$tmpdir/lib/pm-tools" ]
}

@test "uninstall: restores backups if they exist" {
    local tmpdir=$(mktemp -d)
    trap "rm -rf $tmpdir" EXIT

    # Create existing installation
    mkdir -p "$tmpdir/bin"
    echo "old version" > "$tmpdir/bin/pm search"

    # Install (creates backup)
    bash ./install-remote.sh --prefix "$tmpdir" --offline-dir ./

    # Uninstall
    bash ./uninstall.sh --prefix "$tmpdir"

    # Original restored
    [ "$(cat "$tmpdir/bin/pm search")" == "old version" ]
}
```

### Phase 3: Edge Cases

```bash
@test "install-remote: handles spaces in PREFIX path" {
    local tmpdir=$(mktemp -d)
    local spacedir="$tmpdir/my folder"
    mkdir -p "$spacedir"
    trap "rm -rf '$tmpdir'" EXIT

    run bash ./install-remote.sh --prefix "$spacedir" --offline-dir ./
    [ "$status" -eq 0 ]
    [ -x "$spacedir/bin/pm search" ]
}

@test "install-remote: handles interrupted download gracefully" {
    local tmpdir=$(mktemp -d)
    trap "rm -rf $tmpdir" EXIT

    # Simulate interrupted download by providing invalid URL
    run bash ./install-remote.sh --prefix "$tmpdir" --base-url "http://localhost:99999"
    [ "$status" -eq 1 ]

    # Should not leave partial installation
    [ ! -f "$tmpdir/bin/pm search" ]
}

@test "install-remote: version flag shows version" {
    run bash ./install-remote.sh --version
    [ "$status" -eq 0 ]
    [[ "$output" =~ ^[0-9]+\.[0-9]+ ]]
}
```

## Implementation Phases

### Phase 0: Prerequisites (TDD Setup)

- [x] Existing: `bin/` commands work independently
- [x] Existing: `lib/pm-common.sh` is sourceable
- [ ] Create `VERSION` file with initial version (e.g., `1.0.0`)
- [ ] Create test file `test/install-remote.bats`

### Phase 1: Core Functions

#### 1.1 Pre-flight Checks
```bash
# Functions to implement:
check_bash_version()      # Exit if bash < 4.0
check_curl_available()    # Exit if curl not found
check_write_permissions() # Exit if can't write to PREFIX
```

#### 1.2 Dependency Checker
```bash
# Functions to implement:
detect_package_manager()  # Returns: apt, brew, dnf, apk, or unknown
check_required_deps()     # Check xml2, jq, curl, grep
check_optional_deps()     # Check mawk, suggest if missing
format_install_command()  # Platform-specific install instructions
```

#### 1.3 Download Functions
```bash
# Functions to implement:
download_file()           # curl -fsSL with retries and validation
validate_script()         # Check shebang, basic syntax
get_file_list()           # Returns list of files to download
```

### Phase 2: Installation Logic

#### 2.1 Path Rewriting
```bash
# Functions to implement:
rewrite_lib_path()        # Update source paths in commands
```

#### 2.2 File Installation
```bash
# Functions to implement:
create_directories()      # mkdir -p for bin and lib
backup_existing()         # Move existing files to .backup
install_library()         # Install pm-common.sh
install_commands()        # Install all bin/* with path rewriting
set_permissions()         # chmod +x on all commands
```

#### 2.3 Post-install
```bash
# Functions to implement:
verify_installation()     # Test that commands work
show_path_instructions()  # If PREFIX/bin not in PATH
add_to_shell_config()     # Optional: modify .bashrc/.zshrc
```

### Phase 3: Uninstaller

```bash
# uninstall.sh functions:
remove_commands()         # rm bin/pm-*
remove_library()          # rm -rf lib/pm-tools
restore_backups()         # Move .backup files back
clean_shell_config()      # Remove PATH modification
```

### Phase 4: CLI Interface

```bash
# Command-line options:
--prefix PATH      # Installation prefix (default: ~/.local)
--version          # Show version and exit
--help             # Show help and exit
--check-only       # Only run checks, don't install
--check-deps       # Only check dependencies
--uninstall        # Run uninstaller
--offline-dir DIR  # Use local files instead of downloading (for testing)
--base-url URL     # Custom GitHub URL (for forks)
--no-modify-path   # Don't offer to modify shell config
--force            # Overwrite without backup
```

### Phase 5: Polish and Documentation

- [ ] Add progress indicators for downloads
- [ ] Colorized output (with NO_COLOR support)
- [ ] Update README.md with curl install instructions
- [ ] Add CHANGELOG.md
- [ ] Create GitHub release with tags

## Version Numbering

Semantic versioning: `MAJOR.MINOR.PATCH`

| Change Type | Example | Bump |
|-------------|---------|------|
| Breaking change to output format | Remove field from JSON | MAJOR |
| New command or option | Add `pm cite` | MINOR |
| Bug fix, performance | Fix edge case | PATCH |

Initial release: `1.0.0`

## GitHub Repository Setup

### Required for curl install:

1. **Public repository** at known URL
2. **Raw file access** via `raw.githubusercontent.com`
3. **Tagged releases** for version pinning

### Recommended structure:

```
https://github.com/lescientifik/pm-tools/
├── install-remote.sh     # Main installer
├── VERSION               # Version file
├── bin/                  # Commands
├── lib/                  # Libraries
└── releases/             # (via GitHub Releases)
    └── v1.0.0/
        └── checksums.txt # SHA256 of all files
```

### Install URL patterns:

```bash
# Latest (main branch)
curl -fsSL https://raw.githubusercontent.com/USER/pm-tools/main/install-remote.sh | bash

# Specific version
curl -fsSL https://raw.githubusercontent.com/USER/pm-tools/v1.0.0/install-remote.sh | bash

# With options
curl -fsSL .../install-remote.sh | bash -s -- --prefix /opt/pm-tools
```

## Security Considerations

### Implemented

1. **HTTPS only**: All downloads over TLS
2. **Fail-fast**: Exit on any download failure
3. **Validation**: Check shebang before executing
4. **No sudo**: Install to user directory by default
5. **Atomic operations**: Backup before overwrite

### Future (not in initial release)

1. **Checksum verification**: SHA256 of downloaded files
2. **GPG signatures**: Signed releases
3. **Sandboxed preview**: `--dry-run` mode

## Success Criteria

1. **Single command install works**:
   ```bash
   curl -fsSL https://.../install-remote.sh | bash
   pm quick "test"  # Works immediately or shows PATH instruction
   ```

2. **All tests pass**: `bats test/install-remote.bats`

3. **Uninstall is clean**: No orphan files left

4. **Works on target platforms**:
   - Ubuntu 20.04+
   - macOS 12+
   - Debian 11+

5. **Documentation complete**: README shows curl install as primary method

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| GitHub rate limits | Low | Medium | Cache files locally, use releases |
| Network interruption | Medium | Low | Atomic install, cleanup on failure |
| Permission errors | Medium | Medium | Pre-check permissions, clear errors |
| Path conflicts | Low | Low | Backup existing, warn user |
| Broken dependencies | Medium | High | Check deps before install, show fix |

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 0 (Setup) | 0.5 hour | None |
| Phase 1 (Core) | 2 hours | Phase 0 |
| Phase 2 (Install) | 2 hours | Phase 1 |
| Phase 3 (Uninstall) | 1 hour | Phase 2 |
| Phase 4 (CLI) | 1 hour | Phase 2 |
| Phase 5 (Polish) | 1.5 hours | Phase 4 |
| **Total** | **~8 hours** | |

## References

- [Best practices for curl in shell scripts](https://www.joyfulbikeshedding.com/blog/2020-05-11-best-practices-when-using-curl-in-shell-scripts.html)
- [NVM install script](https://github.com/nvm-sh/nvm/blob/master/install.sh) - Shell detection, PATH handling
- [Oh My Zsh installer](https://github.com/ohmyzsh/ohmyzsh/blob/master/tools/install.sh) - Backup strategy, platform detection
- [Chef blog on curl|bash](https://www.chef.io/blog/5-ways-to-deal-with-the-install-sh-curl-pipe-bash-problem) - Security considerations
