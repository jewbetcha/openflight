#!/bin/bash
#
# DIY Golf Launch Monitor - Setup Script
# =======================================
#
# This script sets up the Python environment using uv and installs
# all required dependencies for the golf launch monitor.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
#
# Options:
#   ./setup.sh --phase1    # Install Phase 1 (radar only) dependencies
#   ./setup.sh --phase2    # Install Phase 1 + Phase 2 (camera) dependencies
#   ./setup.sh --all       # Install everything (default)
#

set -e  # Exit on error

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_DIR="$HOME/golf-launch-monitor"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_VERSION="3.11"

# Phase 1 packages (radar only)
PHASE1_PACKAGES=(
    "numpy"
    "scipy"
    "spidev"
)

# Phase 2 packages (camera)
PHASE2_PACKAGES=(
    "opencv-python"
    "picamera2"
    "RPi.GPIO"
)

# =============================================================================
# COLORS AND FORMATTING
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_step() {
    echo -e "${GREEN}▶${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

INSTALL_PHASE1=true
INSTALL_PHASE2=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --phase1)
            INSTALL_PHASE1=true
            INSTALL_PHASE2=false
            shift
            ;;
        --phase2|--all)
            INSTALL_PHASE1=true
            INSTALL_PHASE2=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --phase1    Install Phase 1 (radar only) dependencies"
            echo "  --phase2    Install Phase 1 + Phase 2 (camera) dependencies"
            echo "  --all       Install everything (default)"
            echo "  --help      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# =============================================================================
# MAIN SETUP
# =============================================================================

print_header "🏌️  DIY Golf Launch Monitor - Setup"

echo ""
echo "  Project directory: $PROJECT_DIR"
echo "  Python version:    $PYTHON_VERSION"
echo "  Phase 1 (radar):   $INSTALL_PHASE1"
echo "  Phase 2 (camera):  $INSTALL_PHASE2"
echo ""

# -----------------------------------------------------------------------------
# Check if running on Raspberry Pi
# -----------------------------------------------------------------------------

print_header "Checking System"

if [[ -f /proc/device-tree/model ]]; then
    PI_MODEL=$(cat /proc/device-tree/model)
    print_success "Detected: $PI_MODEL"
else
    print_warning "Not running on Raspberry Pi (some features may not work)"
fi

# Check architecture
ARCH=$(uname -m)
print_step "Architecture: $ARCH"

# -----------------------------------------------------------------------------
# Install uv if not present
# -----------------------------------------------------------------------------

print_header "Setting up uv"

if command -v uv &> /dev/null; then
    UV_VERSION=$(uv --version)
    print_success "uv already installed: $UV_VERSION"
else
    print_step "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
    
    # Add to .bashrc if not already there
    if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' ~/.bashrc 2>/dev/null; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
        print_step "Added uv to PATH in ~/.bashrc"
    fi
    
    print_success "uv installed successfully"
fi

# -----------------------------------------------------------------------------
# Create project directory
# -----------------------------------------------------------------------------

print_header "Creating Project Directory"

if [[ -d "$PROJECT_DIR" ]]; then
    print_warning "Project directory already exists: $PROJECT_DIR"
    read -p "  Overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_step "Keeping existing directory"
    else
        rm -rf "$PROJECT_DIR"
        mkdir -p "$PROJECT_DIR"
        print_success "Created fresh project directory"
    fi
else
    mkdir -p "$PROJECT_DIR"
    print_success "Created: $PROJECT_DIR"
fi

# Create subdirectories
mkdir -p "$PROJECT_DIR/shots"
mkdir -p "$PROJECT_DIR/logs"
print_success "Created subdirectories: shots/, logs/"

# -----------------------------------------------------------------------------
# Create virtual environment
# -----------------------------------------------------------------------------

print_header "Creating Python Environment"

cd "$PROJECT_DIR"

if [[ -d "$VENV_DIR" ]]; then
    print_warning "Virtual environment already exists"
    read -p "  Recreate? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_DIR"
        print_step "Creating new virtual environment with Python $PYTHON_VERSION..."
        uv venv --python "$PYTHON_VERSION" "$VENV_DIR"
        print_success "Virtual environment created"
    fi
else
    print_step "Creating virtual environment with Python $PYTHON_VERSION..."
    uv venv --python "$PYTHON_VERSION" "$VENV_DIR"
    print_success "Virtual environment created"
fi

# -----------------------------------------------------------------------------
# Install Phase 1 packages
# -----------------------------------------------------------------------------

print_header "Installing Phase 1 Packages (Radar)"

for pkg in "${PHASE1_PACKAGES[@]}"; do
    print_step "Installing $pkg..."
    uv pip install --python "$VENV_DIR/bin/python" "$pkg"
done

print_success "Phase 1 packages installed"

# -----------------------------------------------------------------------------
# Install Phase 2 packages (if requested)
# -----------------------------------------------------------------------------

if [[ "$INSTALL_PHASE2" == true ]]; then
    print_header "Installing Phase 2 Packages (Camera)"
    
    for pkg in "${PHASE2_PACKAGES[@]}"; do
        print_step "Installing $pkg..."
        # Some packages might fail on non-Pi systems, that's OK
        uv pip install --python "$VENV_DIR/bin/python" "$pkg" 2>/dev/null || {
            print_warning "Could not install $pkg (may require Raspberry Pi)"
        }
    done
    
    print_success "Phase 2 packages installed (where available)"
fi

# -----------------------------------------------------------------------------
# Copy project files
# -----------------------------------------------------------------------------

print_header "Setting Up Project Files"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Copy Python files if they exist in the same directory as the script
if [[ -f "$SCRIPT_DIR/launch_monitor.py" ]]; then
    cp "$SCRIPT_DIR/launch_monitor.py" "$PROJECT_DIR/"
    print_success "Copied launch_monitor.py"
fi

if [[ -f "$SCRIPT_DIR/diagnose.py" ]]; then
    cp "$SCRIPT_DIR/diagnose.py" "$PROJECT_DIR/"
    print_success "Copied diagnose.py"
fi

# Create a simple run script
cat > "$PROJECT_DIR/run.sh" << 'EOF'
#!/bin/bash
# Quick launcher for the golf launch monitor
cd "$(dirname "$0")"
source .venv/bin/activate
python launch_monitor.py "$@"
EOF
chmod +x "$PROJECT_DIR/run.sh"
print_success "Created run.sh launcher"

# Create diagnose launcher
cat > "$PROJECT_DIR/diagnose.sh" << 'EOF'
#!/bin/bash
# Quick launcher for diagnostics
cd "$(dirname "$0")"
source .venv/bin/activate
python diagnose.py "$@"
EOF
chmod +x "$PROJECT_DIR/diagnose.sh"
print_success "Created diagnose.sh launcher"

# -----------------------------------------------------------------------------
# Enable SPI (if on Raspberry Pi)
# -----------------------------------------------------------------------------

print_header "Checking SPI Configuration"

if [[ -f /boot/config.txt ]] || [[ -f /boot/firmware/config.txt ]]; then
    # Determine config file location (differs between Pi OS versions)
    if [[ -f /boot/firmware/config.txt ]]; then
        CONFIG_FILE="/boot/firmware/config.txt"
    else
        CONFIG_FILE="/boot/config.txt"
    fi
    
    if grep -q "^dtparam=spi=on" "$CONFIG_FILE" 2>/dev/null; then
        print_success "SPI is already enabled"
    else
        print_warning "SPI may not be enabled"
        echo ""
        echo "  To enable SPI, run:"
        echo "    sudo raspi-config"
        echo "    → Interface Options → SPI → Enable"
        echo ""
        echo "  Or add this line to $CONFIG_FILE:"
        echo "    dtparam=spi=on"
        echo ""
        read -p "  Would you like to enable SPI now? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if sudo grep -q "^#dtparam=spi" "$CONFIG_FILE"; then
                sudo sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' "$CONFIG_FILE"
            else
                echo "dtparam=spi=on" | sudo tee -a "$CONFIG_FILE" > /dev/null
            fi
            print_success "SPI enabled - REBOOT REQUIRED"
            NEEDS_REBOOT=true
        fi
    fi
    
    # Check if SPI device exists
    if [[ -e /dev/spidev0.0 ]]; then
        print_success "SPI device found: /dev/spidev0.0"
    else
        print_warning "SPI device not found (reboot may be required)"
    fi
else
    print_warning "Not on Raspberry Pi - skipping SPI check"
fi

# -----------------------------------------------------------------------------
# Create README
# -----------------------------------------------------------------------------

cat > "$PROJECT_DIR/README.md" << 'EOF'
# DIY Golf Launch Monitor

## Quick Start

1. **Run diagnostics first:**
   ```bash
   ./diagnose.sh
   ```

2. **Start the launch monitor:**
   ```bash
   ./run.sh
   ```

## Command Options

### Launch Monitor
```bash
./run.sh                      # Auto-detect and run
./run.sh --phase 1            # Radar only mode
./run.sh --phase 2            # Radar + camera mode
./run.sh --radar cdm324       # Use CDM324 radar (default)
./run.sh --radar hb100        # Use HB100 radar
./run.sh --simulate           # Test without hardware
```

### Diagnostics
```bash
./diagnose.sh                 # Run all tests
./diagnose.sh --spi           # Test SPI/ADC only
./diagnose.sh --radar         # Test radar only
./diagnose.sh --camera        # Test camera only
./diagnose.sh --live          # Live radar signal monitor
./diagnose.sh --adc           # Live ADC value monitor
```

## Project Structure
```
golf-launch-monitor/
├── .venv/              # Python virtual environment
├── shots/              # Saved shot data and images
├── logs/               # Log files
├── launch_monitor.py   # Main application
├── diagnose.py         # Hardware diagnostics
├── run.sh              # Quick launcher
├── diagnose.sh         # Diagnostics launcher
└── README.md           # This file
```

## Hardware Setup

See the wiring guide for detailed connection instructions.

### Pin Connections (MCP3008 to Pi)
| MCP3008 | Pi GPIO |
|---------|---------|
| VDD     | 3.3V (Pin 1) |
| VREF    | 3.3V (Pin 1) |
| AGND    | GND (Pin 6) |
| CLK     | SCLK (Pin 23) |
| DOUT    | MISO (Pin 21) |
| DIN     | MOSI (Pin 19) |
| CS      | CE0 (Pin 24) |
| DGND    | GND (Pin 6) |

### Radar Module
- CDM324 or HB100 → LM358 amp → MCP3008 CH0
EOF

print_success "Created README.md"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

print_header "✅ Setup Complete!"

echo ""
echo "  Project location: $PROJECT_DIR"
echo ""
echo "  To get started:"
echo ""
echo "    cd $PROJECT_DIR"
echo ""
echo "    # Run diagnostics first"
echo "    ./diagnose.sh"
echo ""
echo "    # Then start the launch monitor"
echo "    ./run.sh"
echo ""

if [[ "$NEEDS_REBOOT" == true ]]; then
    echo -e "  ${YELLOW}⚠ REBOOT REQUIRED to enable SPI${NC}"
    echo ""
    read -p "  Reboot now? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo reboot
    fi
fi

echo "  Happy golfing! 🏌️"
echo ""
