#!/usr/bin/env bash
# uninstall.sh - Remove pm-tools installation
#
# Usage: ./uninstall.sh [--prefix PATH]

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_PREFIX="$HOME/.local"
COMMANDS=(pm-search pm-fetch pm-parse pm-filter pm-show pm-download pm-diff pm-quick pm-skill)

# =============================================================================
# Output helpers
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

if [[ -n "${NO_COLOR:-}" ]]; then
    RED='' GREEN='' YELLOW='' NC=''
fi

info()    { echo -e "${GREEN}==>${NC} $*"; }
warn()    { echo -e "${YELLOW}Warning:${NC} $*" >&2; }
error()   { echo -e "${RED}Error:${NC} $*" >&2; }

# =============================================================================
# Help
# =============================================================================

show_help() {
    cat << 'EOF'
uninstall.sh - Remove pm-tools installation

Usage: ./uninstall.sh [OPTIONS]

Options:
  --prefix PATH    Installation prefix (default: ~/.local)
  -h, --help       Show this help

Examples:
  ./uninstall.sh                      # Remove from ~/.local
  ./uninstall.sh --prefix /opt/tools  # Remove from custom location
EOF
    exit 0
}

# =============================================================================
# Main
# =============================================================================

main() {
    local prefix="$DEFAULT_PREFIX"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                show_help
                ;;
            --prefix)
                prefix="$2"
                shift 2
                ;;
            --prefix=*)
                prefix="${1#*=}"
                shift
                ;;
            *)
                error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # Expand ~
    prefix="${prefix/#\~/$HOME}"

    local bin_dir="$prefix/bin"
    local lib_dir="$prefix/lib/pm-tools"
    local removed=0

    # Remove commands
    for cmd in "${COMMANDS[@]}"; do
        if [[ -f "$bin_dir/$cmd" ]]; then
            rm -f "$bin_dir/$cmd"
            info "Removed: $bin_dir/$cmd"
            ((removed++)) || true
        fi
    done

    # Remove library directory
    if [[ -d "$lib_dir" ]]; then
        rm -rf "$lib_dir"
        info "Removed: $lib_dir/"
        ((removed++)) || true
    fi

    echo ""
    if [[ $removed -eq 0 ]]; then
        warn "Nothing to remove. pm-tools not found at $prefix"
    else
        info "Uninstallation complete."
    fi
}

main "$@"
