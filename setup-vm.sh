#!/bin/bash

# ==============================================================================
# Career Scout AI - VM (Ubuntu) Setup Script
# ==============================================================================
# Run this script on your Ubuntu VM from the project root directory:
#   ./setup-vm.sh
# ==============================================================================

set -eo pipefail

# Guard: must be run from the project root
if [ ! -f "pyproject.toml" ]; then
    echo "Error: This script must be run from the project root directory."
    exit 1
fi

# Ensure uv and cargo binaries are findable for the rest of the script
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

echo "======================================================"
echo "Career Scout AI - VM (Ubuntu) Setup Script"
echo "======================================================"

echo ""
echo "1. Installing system dependencies (requires sudo)..."
sudo apt update
sudo apt install -y git curl python3-pip python3-dev rsync

echo ""
echo "2. Checking uv (Python package manager)..."
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo "uv is already installed."
fi

# Persist uv/cargo PATH to ~/.bashrc so it is available in future shell sessions
PATH_LINE='export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"'
if ! grep -qF '.local/bin' ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# Added by career-scout-ai setup script" >> ~/.bashrc
    echo "$PATH_LINE" >> ~/.bashrc
    echo "PATH persisted to ~/.bashrc"
else
    echo "PATH entry already present in ~/.bashrc, skipping."
fi

echo ""
echo "3. Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "Ollama is already installed."
fi

echo ""
echo "4. Ensuring Ollama service is running..."
if ! systemctl is-active --quiet ollama; then
    sudo systemctl enable --now ollama
else
    echo "Ollama service is already running."
fi

echo ""
echo "5. Downloading AI Model (qwen2.5:3b)..."
echo "(This is a ~2.0GB download and might take a while if not cached)"
ollama pull qwen2.5:3b

echo ""
echo "6. Setting up Python virtual environment..."
uv venv --python 3.12
uv sync

echo ""
echo "7. Initializing Database..."
mkdir -p data
if [ -f "alembic.ini" ]; then
    uv run alembic upgrade head
else
    echo "Warning: No alembic.ini found, skipping database migrations."
fi

echo ""
echo "8. Creating .env configuration..."
if [ ! -f ".env" ]; then
    cat <<EOF > .env
APP_NAME=Career Scout AI
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
EOF
    echo ".env file created."
else
    echo ".env file already exists, skipping."
fi

echo ""
echo "9. Installing Systemd Scheduling (Daily at 02:00 Warsaw time)..."
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
echo "Systemd timer enabled successfully."

echo ""
echo "======================================================"
echo "Setup Complete!"
echo "======================================================"
echo "The application will run automatically every day at 02:00 (Warsaw time)."
echo ""
echo "Next scheduled run:"
systemctl --user list-timers career-scout-ai.timer --no-pager 2>/dev/null || true
echo ""
echo "Useful commands:"
echo "  Check timer:      systemctl --user list-timers career-scout-ai.timer"
echo "  View logs:        journalctl --user -u career-scout-ai.service -f"
echo "  Trigger manually: systemctl --user start career-scout-ai.service"
echo "  Disable timer:    systemctl --user disable --now career-scout-ai.timer"
echo "======================================================"
