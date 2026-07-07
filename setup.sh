#!/bin/bash

# ==============================================================================
# Career Scout AI - Setup Script
# ==============================================================================
# Supports: Ubuntu 22.04/24.04 LTS and macOS
#
# Usage:
#   ./setup.sh           Full setup. On Ubuntu: installs systemd scheduling.
#                        On macOS: skips scheduling with a note.
#   ./setup.sh --local   Full setup, scheduling skipped on any OS.
# ==============================================================================

set -eo pipefail

# ------------------------------------------------------------------------------
# 1. Parse arguments
# ------------------------------------------------------------------------------
LOCAL_MODE=false
for arg in "$@"; do
    if [ "$arg" = "--local" ]; then
        LOCAL_MODE=true
    fi
done

# ------------------------------------------------------------------------------
# 2. Detect OS
# ------------------------------------------------------------------------------
UNAME_OUT="$(uname -s)"
case "$UNAME_OUT" in
    Linux*)   OS="ubuntu" ;;
    Darwin*)  OS="macos" ;;
    *)
        echo "Error: Unsupported operating system: $UNAME_OUT"
        echo "This script supports Ubuntu 22.04/24.04 LTS and macOS only."
        exit 1
        ;;
esac

# ------------------------------------------------------------------------------
# 3. Guard: must be run from the project root
# ------------------------------------------------------------------------------
if [ ! -f "pyproject.toml" ]; then
    echo "Error: This script must be run from the project root directory."
    exit 1
fi

# ------------------------------------------------------------------------------
# 4. Ensure uv and cargo binaries are findable for the rest of the script
# ------------------------------------------------------------------------------
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

echo "======================================================"
echo "Career Scout AI - Setup Script"
echo "OS: $UNAME_OUT | Local mode: $LOCAL_MODE"
echo "======================================================"

# ------------------------------------------------------------------------------
# 5. Install system dependencies
# ------------------------------------------------------------------------------
echo ""
echo "1. Installing system dependencies..."

if [ "$OS" = "ubuntu" ]; then
    sudo apt update
    sudo apt install -y curl git
elif [ "$OS" = "macos" ]; then
    if ! command -v brew &> /dev/null; then
        echo ""
        echo "Error: Homebrew is not installed."
        echo "Install it first, then re-run this script:"
        echo ""
        echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        echo ""
        echo "More info: https://brew.sh"
        exit 1
    fi
    brew install git curl
fi

# ------------------------------------------------------------------------------
# 6. Install uv (Python package manager)
# ------------------------------------------------------------------------------
echo ""
echo "2. Checking uv (Python package manager)..."
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo "uv is already installed."
fi

# ------------------------------------------------------------------------------
# 7. Persist uv PATH to shell rc file
# ------------------------------------------------------------------------------
PATH_LINE='export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"'

if [[ "$SHELL" == *"zsh"* ]]; then
    RC_FILE="$HOME/.zshrc"
else
    RC_FILE="$HOME/.bashrc"
fi

if ! grep -qF '.local/bin' "$RC_FILE" 2>/dev/null; then
    echo "" >> "$RC_FILE"
    echo "# Added by career-scout-ai setup script" >> "$RC_FILE"
    echo "$PATH_LINE" >> "$RC_FILE"
    echo "PATH persisted to $RC_FILE"
else
    echo "PATH entry already present in $RC_FILE, skipping."
fi

# ------------------------------------------------------------------------------
# 8. Set up Python virtual environment
# ------------------------------------------------------------------------------
echo ""
echo "3. Setting up Python virtual environment..."
uv venv --python 3.12
uv sync

# ------------------------------------------------------------------------------
# 9. Initialize database
# ------------------------------------------------------------------------------
echo ""
echo "4. Initializing database..."
mkdir -p data
if [ -f "alembic.ini" ]; then
    uv run alembic upgrade head
else
    echo "Warning: No alembic.ini found, skipping database migrations."
fi

# ------------------------------------------------------------------------------
# 10. Create .env configuration
# ------------------------------------------------------------------------------
echo ""
echo "5. Creating .env configuration..."
if [ ! -f ".env" ]; then
    cat <<EOF > .env
APP_NAME=Career Scout AI
EOF
    echo ".env file created."
else
    echo ".env file already exists, skipping."
fi

# ------------------------------------------------------------------------------
# 11. Background scheduling
# ------------------------------------------------------------------------------
echo ""
echo "6. Background scheduling..."

if [ "$LOCAL_MODE" = true ]; then
    echo "Scheduling skipped (--local mode)."
elif [ "$OS" = "ubuntu" ]; then
    if [ ! -f "deploy/career-scout-ai.service" ] || [ ! -f "deploy/career-scout-ai.timer" ]; then
        echo "Error: deploy/ unit files not found. Cannot install timer."
        exit 1
    fi

    SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_USER_DIR"

    sed "s|__PROJECT_DIR__|$PWD|g" deploy/career-scout-ai.service > "$SYSTEMD_USER_DIR/career-scout-ai.service"
    cp deploy/career-scout-ai.timer "$SYSTEMD_USER_DIR/career-scout-ai.timer"

    sudo loginctl enable-linger "$USER"
    systemctl --user daemon-reload
    systemctl --user enable --now career-scout-ai.timer
    echo "Systemd timer enabled. Application will run daily at 02:00 (Warsaw time)."
else
    # macOS without --local
    echo ""
    echo "NOTE: Scheduling skipped — systemd is not available on macOS."
    echo "      Run the application manually with: uv run career-scout-ai"
    echo "      Use --local to suppress this message in future runs."
    echo "      For automated scheduling on macOS, see docs/setup-guide.md Section 4."
fi

# ------------------------------------------------------------------------------
# 12. Summary
# ------------------------------------------------------------------------------
echo ""
echo "======================================================"
echo "Setup Complete!"
echo "======================================================"
echo ""
echo "Reload your shell to pick up the updated PATH:"
echo "  source $RC_FILE"
echo ""
if [ "$LOCAL_MODE" = false ] && [ "$OS" = "ubuntu" ]; then
    echo "The application will run automatically every day at 02:00 (Warsaw time)."
    echo ""
    echo "Useful commands:"
    echo "  Check timer:      systemctl --user list-timers career-scout-ai.timer"
    echo "  View logs:        journalctl --user -u career-scout-ai.service -f"
    echo "  Trigger manually: systemctl --user start career-scout-ai.service"
    echo "  Disable timer:    systemctl --user disable --now career-scout-ai.timer"
else
    echo "Run the application manually:"
    echo "  uv run career-scout-ai"
fi
echo "======================================================"
