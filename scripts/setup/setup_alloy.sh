#!/bin/bash
#
# Setup Grafana Alloy on Raspberry Pi for OpenFlight log shipping
#
# This script installs Grafana Alloy and configures it to tail OpenFlight
# session logs and ship them to Grafana Cloud Loki.
#
# Usage:
#   sudo ./scripts/setup/setup_alloy.sh
#
# After running this script:
#   1. Edit /etc/alloy/credentials.env with your Grafana Cloud credentials
#   2. Start with: sudo systemctl start alloy
#   3. Or just run scripts/start-kiosk.sh (it starts Alloy automatically)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo -e "${GREEN}=== OpenFlight Alloy Setup ===${NC}"

# Get the actual user (not root when running with sudo)
OPENFLIGHT_USER=${SUDO_USER:-$USER}
OPENFLIGHT_HOME=$(eval echo ~$OPENFLIGHT_USER)
LOG_DIR="$OPENFLIGHT_HOME/openflight_sessions"

echo "OpenFlight user: $OPENFLIGHT_USER"
echo "Log directory: $LOG_DIR"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root: sudo $0${NC}"
    exit 1
fi

# Step 1: Add Grafana APT repository
echo -e "\n${GREEN}[1/5] Adding Grafana APT repository...${NC}"
apt-get install -y wget gpg

mkdir -p /etc/apt/keyrings/
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor > /etc/apt/keyrings/grafana.gpg

echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list

apt-get update

# Step 2: Install Alloy
echo -e "\n${GREEN}[2/5] Installing Grafana Alloy...${NC}"
apt-get install -y alloy

# Step 3: Create Alloy configuration
echo -e "\n${GREEN}[3/5] Creating Alloy configuration...${NC}"

mkdir -p /etc/alloy

# Generate config with the correct log directory path
sed "s|/home/coleman/openflight_sessions|${LOG_DIR}|g" \
    "$PROJECT_DIR/config/alloy.alloy" > /etc/alloy/config.alloy

echo "Configuration written to /etc/alloy/config.alloy"
echo "  (source: $PROJECT_DIR/config/alloy.alloy)"

# Step 4: Create credentials template
echo -e "\n${GREEN}[4/5] Creating credentials template...${NC}"

if [ ! -f /etc/alloy/credentials.env ]; then
    cp "$PROJECT_DIR/config/credentials.env.example" /etc/alloy/credentials.env
    chmod 600 /etc/alloy/credentials.env
    echo -e "${YELLOW}Created /etc/alloy/credentials.env — edit with your Grafana Cloud credentials${NC}"
else
    echo "Credentials file already exists, not overwriting"
fi

# Step 5: Configure systemd service
echo -e "\n${GREEN}[5/5] Configuring systemd service...${NC}"

mkdir -p /etc/systemd/system/alloy.service.d

cat > /etc/systemd/system/alloy.service.d/override.conf << EOF
[Service]
# Load Grafana Cloud credentials
EnvironmentFile=/etc/alloy/credentials.env

# Run as the openflight user to access log files
User=$OPENFLIGHT_USER
Group=$OPENFLIGHT_USER

# Ensure we can read log files
ReadOnlyPaths=$LOG_DIR
EOF

# Ensure log directory exists
mkdir -p "$LOG_DIR"
chown "$OPENFLIGHT_USER:$OPENFLIGHT_USER" "$LOG_DIR"

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable alloy

echo -e "\n${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit /etc/alloy/credentials.env with your Grafana Cloud credentials"
echo "     Get these from: Grafana Cloud -> Connections -> Loki -> Details"
echo ""
echo "  2. Start Alloy:"
echo "     sudo systemctl start alloy"
echo ""
echo "  3. Or just run start-kiosk.sh — it starts Alloy automatically"
echo ""
echo "  4. Verify logs in Grafana Cloud:"
echo "     Query: {app=\"openflight\"}"
echo ""
echo -e "${YELLOW}Note: Alloy will start shipping logs once credentials are configured${NC}"
