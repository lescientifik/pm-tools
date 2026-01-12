#!/usr/bin/env bash
# install-remote.sh - Install pm-tools from GitHub (or locally for testing)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/USER/pubmed_parser/main/install-remote.sh | bash
#   ./install-remote.sh --offline --prefix ~/.local
#
# Options:
#   --prefix PATH       Installation prefix (default: ~/.local)
#   --offline           Install from local files (for testing)
#   --check-only        Run checks without installing
#   --check-deps        Only check dependencies
#   --no-modify-path    Don't prompt to modify shell config
#   --base-url URL      Custom GitHub raw URL (for forks)
#   -h, --help          Show this help
#   --version           Show version

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

VERSION="1.0.0"
DEFAULT_PREFIX="$HOME/.local"
DEFAULT_BASE_URL="https://raw.githubusercontent.com/USER/pubmed_parser/main"

# Files to install
COMMANDS=(pm-search pm-fetch pm-parse pm-filter pm-show pm-download pm-diff pm-quick pm-skill)
# Library path (relative to source)
# shellcheck disable=SC2034
LIBRARY="lib/pm-common.sh"

# =============================================================================
# Output helpers
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Respect NO_COLOR
if [[ -n "${NO_COLOR:-}" ]]; then
    RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

info()    { echo -e "${BLUE}==>${NC} $*"; }
success() { echo -e "${GREEN}==>${NC} $*"; }
warn()    { echo -e "${YELLOW}Warning:${NC} $*" >&2; }
error()   { echo -e "${RED}Error:${NC} $*" >&2; }
die()     { error "$@"; exit 1; }

# =============================================================================
# Help and version
# =============================================================================

show_help() {
    cat << 'EOF'
install-remote.sh - Install pm-tools (PubMed CLI tools)

Usage:
  curl -fsSL https://raw.githubusercontent.com/.../install-remote.sh | bash
  ./install-remote.sh [OPTIONS]

Options:
  --prefix PATH       Installation prefix (default: ~/.local)
  --offline           Install from local files (for testing)
  --check-only        Run checks without installing
  --check-deps        Only show dependency status
  --no-modify-path    Don't prompt to modify shell config
  --base-url URL      Custom GitHub raw URL (for forks)
  -h, --help          Show this help
  --version           Show version

Examples:
  # Install to default location (~/.local)
  curl -fsSL .../install-remote.sh | bash

  # Install to custom prefix
  curl -fsSL .../install-remote.sh | bash -s -- --prefix /opt/pm-tools

  # Test locally without downloading
  ./install-remote.sh --offline --prefix ./test-install
EOF
    exit 0
}

show_version() {
    echo "$VERSION"
    exit 0
}

# =============================================================================
# Pre-flight checks
# =============================================================================

check_bash_version() {
    local major="${BASH_VERSION%%.*}"
    if [[ "$major" -lt 4 ]]; then
        die "Bash 4.0+ required (found $BASH_VERSION)"
    fi
}

check_curl() {
    if ! command -v curl &>/dev/null; then
        die "curl is required but not installed"
    fi
}

check_write_permission() {
    local prefix="$1"
    local test_dir="$prefix"

    # Find the first existing parent directory
    while [[ ! -d "$test_dir" ]] && [[ "$test_dir" != "/" ]]; do
        test_dir="$(dirname "$test_dir")"
    done

    if [[ ! -w "$test_dir" ]]; then
        die "Cannot write to $prefix (no permission on $test_dir)"
    fi
}

run_preflight_checks() {
    local prefix="$1"
    check_bash_version
    check_curl
    check_write_permission "$prefix"
}

# =============================================================================
# Dependency checking
# =============================================================================

detect_package_manager() {
    if command -v apt &>/dev/null; then
        echo "apt"
    elif command -v brew &>/dev/null; then
        echo "brew"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v apk &>/dev/null; then
        echo "apk"
    else
        echo "unknown"
    fi
}

get_install_command() {
    local pkg_manager="$1"
    shift
    local packages=("$@")

    case "$pkg_manager" in
        apt)  echo "sudo apt install ${packages[*]}" ;;
        brew) echo "brew install ${packages[*]}" ;;
        dnf)  echo "sudo dnf install ${packages[*]}" ;;
        apk)  echo "apk add ${packages[*]}" ;;
        *)    echo "# Install: ${packages[*]}" ;;
    esac
}

check_dependencies() {
    local missing=()
    local pkg_manager
    pkg_manager=$(detect_package_manager)

    echo "Checking dependencies..."
    echo ""

    # Required dependencies
    for dep in curl xml2 jq grep; do
        if command -v "$dep" &>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $dep"
        else
            echo -e "  ${RED}✗${NC} $dep (required)"
            missing+=("$dep")
        fi
    done

    # Optional dependencies
    echo ""
    echo "Optional (for better performance):"
    if command -v mawk &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} mawk"
    else
        echo -e "  ${YELLOW}○${NC} mawk (optional - 2x faster parsing)"
    fi

    echo ""

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "Missing required dependencies: ${missing[*]}"
        echo ""
        echo "Install with:"
        echo "  $(get_install_command "$pkg_manager" "${missing[@]}")"
        return 1
    fi

    echo "All required dependencies installed."
    return 0
}

# =============================================================================
# Download functions
# =============================================================================

download_file() {
    local url="$1"
    local dest="$2"

    if ! curl -fsSL "$url" -o "$dest"; then
        die "Failed to download: $url"
    fi

    # Validate it's a shell script (not a 404 HTML page)
    if ! head -1 "$dest" | grep -q '^#!'; then
        rm -f "$dest"
        die "Downloaded file is not a valid script: $url"
    fi
}

# =============================================================================
# Installation
# =============================================================================

install_from_local() {
    local source_dir="$1"
    local prefix="$2"
    local bin_dir="$prefix/bin"
    local lib_dir="$prefix/lib/pm-tools"

    info "Installing from local files..."

    # Create directories
    mkdir -p "$bin_dir" "$lib_dir"

    # Install library
    cp "$source_dir/lib/pm-common.sh" "$lib_dir/"
    info "Installed: $lib_dir/pm-common.sh"

    # Install commands with path rewriting
    for cmd in "${COMMANDS[@]}"; do
        sed "s|source \"\${SCRIPT_DIR}/../lib/pm-common.sh\"|source \"$lib_dir/pm-common.sh\"|" \
            "$source_dir/bin/$cmd" > "$bin_dir/$cmd"
        chmod +x "$bin_dir/$cmd"
        info "Installed: $bin_dir/$cmd"
    done
}

install_from_remote() {
    local base_url="$1"
    local prefix="$2"
    local bin_dir="$prefix/bin"
    local lib_dir="$prefix/lib/pm-tools"
    local temp_dir

    temp_dir=$(mktemp -d)
    # shellcheck disable=SC2064
    trap "rm -rf '$temp_dir'" EXIT

    info "Downloading pm-tools..."

    # Create directories
    mkdir -p "$bin_dir" "$lib_dir" "$temp_dir/bin" "$temp_dir/lib"

    # Download library
    download_file "$base_url/lib/pm-common.sh" "$temp_dir/lib/pm-common.sh"

    # Download commands
    for cmd in "${COMMANDS[@]}"; do
        download_file "$base_url/bin/$cmd" "$temp_dir/bin/$cmd"
    done

    # Install library
    cp "$temp_dir/lib/pm-common.sh" "$lib_dir/"
    info "Installed: $lib_dir/pm-common.sh"

    # Install commands with path rewriting
    for cmd in "${COMMANDS[@]}"; do
        sed "s|source \"\${SCRIPT_DIR}/../lib/pm-common.sh\"|source \"$lib_dir/pm-common.sh\"|" \
            "$temp_dir/bin/$cmd" > "$bin_dir/$cmd"
        chmod +x "$bin_dir/$cmd"
        info "Installed: $bin_dir/$cmd"
    done
}

# =============================================================================
# Post-install
# =============================================================================

show_path_instructions() {
    local bin_dir="$1"
    local modify_path="$2"

    # Check if already in PATH
    if [[ ":$PATH:" == *":$bin_dir:"* ]]; then
        return 0
    fi

    echo ""
    echo "Add this to your PATH to use pm-tools:"
    echo ""
    echo "  export PATH=\"$bin_dir:\$PATH\""
    echo ""

    # Prompt to add to shell config if allowed
    if [[ "$modify_path" == "true" ]] && [[ -t 0 ]]; then
        local shell_rc=""
        if [[ -n "${ZSH_VERSION:-}" ]] || [[ "$SHELL" == *"zsh"* ]]; then
            shell_rc="$HOME/.zshrc"
        else
            shell_rc="$HOME/.bashrc"
        fi

        echo -n "Add to $shell_rc? [y/N] "
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            {
                echo ""
                echo "# pm-tools"
                echo "export PATH=\"$bin_dir:\$PATH\""
            } >> "$shell_rc"
            success "Added to $shell_rc. Run 'source $shell_rc' or restart your shell."
        fi
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    local prefix="$DEFAULT_PREFIX"
    local base_url="$DEFAULT_BASE_URL"
    local offline=false
    local check_only=false
    local check_deps=false
    local modify_path=true

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                show_help
                ;;
            --version)
                show_version
                ;;
            --prefix)
                prefix="$2"
                shift 2
                ;;
            --prefix=*)
                prefix="${1#*=}"
                shift
                ;;
            --base-url)
                base_url="$2"
                shift 2
                ;;
            --base-url=*)
                base_url="${1#*=}"
                shift
                ;;
            --offline)
                offline=true
                shift
                ;;
            --check-only)
                check_only=true
                shift
                ;;
            --check-deps)
                check_deps=true
                shift
                ;;
            --no-modify-path)
                modify_path=false
                shift
                ;;
            -*)
                die "Unknown option: $1. Use --help for usage."
                ;;
            *)
                die "Unknown argument: $1. Use --help for usage."
                ;;
        esac
    done

    # Expand ~ in prefix
    prefix="${prefix/#\~/$HOME}"

    # Mode: check dependencies only
    if [[ "$check_deps" == "true" ]]; then
        check_dependencies
        exit $?
    fi

    # Run pre-flight checks
    run_preflight_checks "$prefix"

    # Mode: check only
    if [[ "$check_only" == "true" ]]; then
        success "All checks passed."
        exit 0
    fi

    # Check dependencies before installing
    if ! check_dependencies; then
        die "Please install missing dependencies first."
    fi

    # Install
    if [[ "$offline" == "true" ]]; then
        # Determine source directory (where this script is)
        local source_dir
        source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        install_from_local "$source_dir" "$prefix"
    else
        install_from_remote "$base_url" "$prefix"
    fi

    echo ""
    success "Installation complete!"

    # Show PATH instructions
    show_path_instructions "$prefix/bin" "$modify_path"
}

main "$@"
