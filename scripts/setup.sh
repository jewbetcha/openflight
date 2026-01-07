#!/bin/bash
#
# OpenFlight Setup Script
# Installs all Python and Node.js dependencies for first-time setup
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[OpenFlight]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[OpenFlight]${NC} $1"
}

error() {
    echo -e "${RED}[OpenFlight]${NC} $1"
}

info() {
    echo -e "${BLUE}[OpenFlight]${NC} $1"
}

cd "$PROJECT_DIR"

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         OpenFlight Setup Script           ║${NC}"
echo -e "${GREEN}║     DIY Golf Launch Monitor Setup         ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════╝${NC}"
echo ""

# Detect platform
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="linux"
    if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
        PLATFORM="pi"
        log "Detected Raspberry Pi"
    else
        log "Detected Linux"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="macos"
    log "Detected macOS"
else
    PLATFORM="unknown"
    warn "Unknown platform: $OSTYPE"
fi

# Check for Python 3.9+
log "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 9 ]; then
        log "Python $PYTHON_VERSION found ✓"
    else
        error "Python 3.9+ required, found $PYTHON_VERSION"
        exit 1
    fi
else
    error "Python 3 not found. Please install Python 3.9+"
    exit 1
fi

# Check for Node.js
log "Checking Node.js..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    log "Node.js $NODE_VERSION found ✓"
else
    error "Node.js not found. Please install Node.js 18+"
    if [ "$PLATFORM" == "pi" ]; then
        info "On Raspberry Pi, run: sudo apt install nodejs npm"
    elif [ "$PLATFORM" == "macos" ]; then
        info "On macOS, run: brew install node"
    fi
    exit 1
fi

# Check for npm
if ! command -v npm &> /dev/null; then
    error "npm not found. Please install npm"
    exit 1
fi

# Install uv if not present (for faster pip installs)
if ! command -v uv &> /dev/null; then
    log "Installing uv (fast Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Source the new path
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Create virtual environment
log "Creating Python virtual environment..."
if [ "$PLATFORM" == "pi" ]; then
    # On Pi, use system-site-packages for picamera2
    python3 -m venv .venv --system-site-packages
    log "Created venv with system-site-packages (for picamera2)"
else
    python3 -m venv .venv
    log "Created venv"
fi

# Activate venv
source .venv/bin/activate
log "Activated virtual environment"

# Install Python dependencies
log "Installing Python dependencies..."
if command -v uv &> /dev/null; then
    uv pip install -e ".[ui]"

    # Install camera dependencies on Pi or if requested
    if [ "$PLATFORM" == "pi" ]; then
        log "Installing camera dependencies for Raspberry Pi..."
        # Install libcap-dev for picamera2 if not present
        if ! dpkg -s libcap-dev &> /dev/null 2>&1; then
            warn "Installing libcap-dev (requires sudo)..."
            sudo apt install -y libcap-dev
        fi
        uv pip install -e ".[camera]"
    fi
else
    pip install -e ".[ui]"
    if [ "$PLATFORM" == "pi" ]; then
        pip install -e ".[camera]"
    fi
fi
log "Python dependencies installed ✓"

# Install dev dependencies
log "Installing development dependencies..."
if command -v uv &> /dev/null; then
    uv pip install pytest ruff pylint
else
    pip install pytest ruff pylint
fi
log "Dev dependencies installed ✓"

# Install Node.js dependencies and build UI
log "Installing Node.js dependencies..."
cd ui
npm install
log "Node.js dependencies installed ✓"

log "Building UI..."
npm run build
log "UI built ✓"
cd ..

# Make scripts executable
log "Making scripts executable..."
chmod +x scripts/*.sh

# Run tests to verify installation
log "Running tests to verify installation..."
if python -m pytest tests/ -q --tb=no; then
    log "All tests passed ✓"
else
    warn "Some tests failed - installation may be incomplete"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Setup Complete! 🎉                ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════╝${NC}"
echo ""
log "To activate the virtual environment:"
echo "    source .venv/bin/activate"
echo ""
log "To start the server:"
echo "    openflight-server              # With radar"
echo "    openflight-server --mock       # Mock mode (no radar)"
echo ""
log "To run in kiosk mode:"
echo "    ./scripts/start-kiosk.sh"
echo ""
if [ "$PLATFORM" == "pi" ]; then
    log "To set up auto-start on boot:"
    echo "    sudo cp scripts/openflight.service /etc/systemd/system/"
    echo "    sudo systemctl daemon-reload"
    echo "    sudo systemctl enable openflight"
    echo ""
    log "To add desktop shortcut:"
    echo "    cp scripts/OpenFlight.desktop ~/Desktop/"
    echo "    chmod +x ~/Desktop/OpenFlight.desktop"
    echo ""
fi
log "For more info, see docs/raspberry-pi-setup.md"
echo ""
