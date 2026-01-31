#!/bin/bash
# BrainBot Daemon Launcher
# ========================
# Starts the BrainBot autonomous daemon

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Check for required Python version
python3 -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'" 2>/dev/null || {
    echo "Error: Python 3.10 or higher is required"
    exit 1
}

# Parse arguments
FOREGROUND=""
if [ "$1" = "-f" ] || [ "$1" = "--foreground" ]; then
    FOREGROUND="--foreground"
fi

# Run the daemon
exec python3 -m brainbot start $FOREGROUND "$@"
