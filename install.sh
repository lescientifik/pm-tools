#!/usr/bin/env bash
# install.sh - Install pm-* tools to ~/.local/bin
#
# Usage: ./install.sh [--prefix /path]
#
# Default: installs to ~/.local/bin and ~/.local/lib/pm-tools

set -euo pipefail

PREFIX="${HOME}/.local"
BIN_DIR="${PREFIX}/bin"
LIB_DIR="${PREFIX}/lib/pm-tools"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            PREFIX="$2"
            BIN_DIR="${PREFIX}/bin"
            LIB_DIR="${PREFIX}/lib/pm-tools"
            shift 2
            ;;
        --prefix=*)
            PREFIX="${1#*=}"
            BIN_DIR="${PREFIX}/bin"
            LIB_DIR="${PREFIX}/lib/pm-tools"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--prefix /path]"
            echo ""
            echo "Install pm-search, pm-fetch, pm-parse to your system."
            echo ""
            echo "Options:"
            echo "  --prefix PATH  Installation prefix (default: ~/.local)"
            echo ""
            echo "Files installed:"
            echo "  \${PREFIX}/bin/pm-search"
            echo "  \${PREFIX}/bin/pm-fetch"
            echo "  \${PREFIX}/bin/pm-parse"
            echo "  \${PREFIX}/lib/pm-tools/pm-common.sh"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Get source directory
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing pm-tools to ${PREFIX}..."

# Create directories
mkdir -p "$BIN_DIR" "$LIB_DIR"

# Install library
cp "${SOURCE_DIR}/lib/pm-common.sh" "${LIB_DIR}/"
echo "  Installed: ${LIB_DIR}/pm-common.sh"

# Install binaries with updated library path
for cmd in pm-search pm-fetch pm-parse pm-show; do
    # Update the source path in the script
    sed "s|source \"\${SCRIPT_DIR}/../lib/pm-common.sh\"|source \"${LIB_DIR}/pm-common.sh\"|" \
        "${SOURCE_DIR}/bin/${cmd}" > "${BIN_DIR}/${cmd}"
    chmod +x "${BIN_DIR}/${cmd}"
    echo "  Installed: ${BIN_DIR}/${cmd}"
done

echo ""
echo "Installation complete!"
echo ""

# Check if bin dir is in PATH
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    echo "Add this to your ~/.bashrc or ~/.zshrc:"
    echo ""
    echo "  export PATH=\"${BIN_DIR}:\$PATH\""
    echo ""
    echo "Then run: source ~/.bashrc"
fi
