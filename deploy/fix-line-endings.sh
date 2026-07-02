#!/usr/bin/env bash
#
# Fix CRLF line endings in shell scripts after transferring from Windows.
# Run this on Linux before running install.sh or update.sh
#
# Usage:
#   bash deploy/fix-line-endings.sh

set -e

echo "Fixing line endings in deploy scripts..."

# Get the directory where this script is located
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Fix all shell scripts in deploy/
for script in "$DEPLOY_DIR"/*.sh; do
    if [ -f "$script" ]; then
        echo "  Processing: $(basename "$script")"
        # Use sed to convert CRLF to LF
        sed -i 's/\r$//' "$script"
        # Ensure executable
        chmod +x "$script"
    fi
done

echo "Done! You can now run install.sh or update.sh"
