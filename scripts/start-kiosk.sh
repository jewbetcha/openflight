#!/bin/bash
#
# OpenFlight Kiosk Startup Script
# Starts the radar server and launches Chromium in kiosk mode
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PORT=8080
HOST="localhost"
MOCK_MODE=false
RADAR_LOG=false
DEBUG_MODE=false
NO_CAMERA=true  # Camera disabled by default (K-LD7 radar handles angle)
# Rolling buffer mode is the only mode (streaming mode removed)
TRIGGER="sound"  # Default: hardware sound trigger (SEN-14262 → HOST_INT)
SOUND_PRE_TRIGGER=""
BUFFER_SPLIT=""
KLD7=false
KLD7_PORT=""
KLD7_ORIENTATION=""
KLD7_SECONDARY_PORT=""
KLD7_SECONDARY_ORIENTATION=""

# Buffer split presets (pre/post trigger segments out of 32 total)
# At 20ksps: each segment = 6.4ms, total buffer = 204.8ms
# At 30ksps: each segment = 4.27ms, total buffer = 136.5ms
#
#   balanced  = S#16 — 50/50 split (recommended starting point)
#   post-heavy = S#12 — 37/63 split (more ball flight, less backswing)
#   pre-heavy  = S#24 — 75/25 split (more backswing, some ball flight)
resolve_buffer_split() {
    case "$1" in
        balanced)   echo 16 ;;
        post-heavy) echo 12 ;;
        pre-heavy)  echo 24 ;;
        *)          echo "$1" ;;  # raw number passthrough
    esac
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mock|-m)
            MOCK_MODE=true
            shift
            ;;
        --radar-log)
            RADAR_LOG=true
            shift
            ;;
        --debug|-d)
            DEBUG_MODE=true
            shift
            ;;
        --no-camera)
            NO_CAMERA=true
            shift
            ;;
        --mode)
            echo "Warning: --mode is deprecated, rolling-buffer is the only mode"
            shift 2
            ;;
        --trigger)
            TRIGGER="$2"
            shift 2
            ;;
        --sound-pre-trigger)
            SOUND_PRE_TRIGGER="$2"
            shift 2
            ;;
        --buffer-split)
            BUFFER_SPLIT="$2"
            shift 2
            ;;
        --sample-rate)
            SAMPLE_RATE="$2"
            shift 2
            ;;
        --kld7)
            KLD7=true
            shift
            ;;
        --kld7-port)
            KLD7_PORT="$2"
            shift 2
            ;;
        --kld7-orientation)
            KLD7_ORIENTATION="$2"
            shift 2
            ;;
        --kld7-secondary-port)
            KLD7_SECONDARY_PORT="$2"
            shift 2
            ;;
        --kld7-secondary-orientation)
            KLD7_SECONDARY_ORIENTATION="$2"
            shift 2
            ;;
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Resolve buffer split preset to a number (overrides --sound-pre-trigger)
if [ -n "$BUFFER_SPLIT" ]; then
    SOUND_PRE_TRIGGER=$(resolve_buffer_split "$BUFFER_SPLIT")
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

cleanup() {
    log "Shutting down..."
    if [ -n "$SERVER_PID" ]; then
        kill $SERVER_PID 2>/dev/null || true
    fi
    if [ -n "$BROWSER_PID" ]; then
        kill $BROWSER_PID 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

cd "$PROJECT_DIR"

# Check if venv exists
if [ ! -d ".venv" ]; then
    error "Virtual environment not found. Run: uv venv && uv pip install -e '.[ui]'"
    exit 1
fi

# Activate venv
source .venv/bin/activate

# Check if UI is built
if [ ! -d "ui/dist" ]; then
    warn "UI not built. Building now..."
    cd ui
    npm install
    npm run build
    cd ..
fi

# Build server command
SERVER_CMD="openflight-server --web-port $PORT"

if [ "$MOCK_MODE" = true ]; then
    SERVER_CMD="$SERVER_CMD --mock"
fi

if [ "$RADAR_LOG" = true ]; then
    SERVER_CMD="$SERVER_CMD --radar-log"
fi

if [ "$DEBUG_MODE" = true ]; then
    SERVER_CMD="$SERVER_CMD --debug"
fi

if [ "$NO_CAMERA" = true ]; then
    SERVER_CMD="$SERVER_CMD --no-camera"
fi

if [ -n "$TRIGGER" ]; then
    SERVER_CMD="$SERVER_CMD --trigger $TRIGGER"
fi

if [ -n "$SOUND_PRE_TRIGGER" ]; then
    SERVER_CMD="$SERVER_CMD --sound-pre-trigger $SOUND_PRE_TRIGGER"
fi

if [ -n "$SAMPLE_RATE" ]; then
    SERVER_CMD="$SERVER_CMD --sample-rate $SAMPLE_RATE"
fi

if [ "$KLD7" = true ]; then
    SERVER_CMD="$SERVER_CMD --kld7"
fi

if [ -n "$KLD7_PORT" ]; then
    SERVER_CMD="$SERVER_CMD --kld7-port $KLD7_PORT"
fi

if [ -n "$KLD7_ORIENTATION" ]; then
    SERVER_CMD="$SERVER_CMD --kld7-orientation $KLD7_ORIENTATION"
fi

if [ -n "$KLD7_SECONDARY_PORT" ]; then
    SERVER_CMD="$SERVER_CMD --kld7-secondary-port $KLD7_SECONDARY_PORT"
fi

if [ -n "$KLD7_SECONDARY_ORIENTATION" ]; then
    SERVER_CMD="$SERVER_CMD --kld7-secondary-orientation $KLD7_SECONDARY_ORIENTATION"
fi

# Start Grafana Alloy for log shipping (if installed and credentials configured)
if command -v alloy &> /dev/null || systemctl is-enabled alloy &> /dev/null 2>&1; then
    if sudo test -f /etc/alloy/credentials.env; then
        # Check if credentials are actually filled in (not just the template)
        if sudo grep -q "LOKI_URL=https\?://" /etc/alloy/credentials.env 2>/dev/null; then
            if ! systemctl is-active alloy &> /dev/null 2>&1; then
                log "Starting Grafana Alloy for log shipping..."
                sudo systemctl start alloy 2>/dev/null || warn "Failed to start Alloy (try: sudo systemctl start alloy)"
            else
                log "Grafana Alloy already running (log shipping active)"
            fi
        else
            warn "Alloy installed but credentials not configured (/etc/alloy/credentials.env)"
        fi
    else
        warn "Alloy installed but no credentials file found (run: sudo scripts/setup_alloy.sh)"
    fi
else
    warn "Grafana Alloy not installed — session logs will only be saved locally"
    warn "  Install with: sudo scripts/setup_alloy.sh"
fi

# Start the server
if [ "$MOCK_MODE" = true ]; then
    log "Starting OpenFlight server on port $PORT (MOCK MODE)..."
else
    log "Starting OpenFlight server on port $PORT..."
    if [ -n "$TRIGGER" ]; then
        log "Trigger: $TRIGGER"
    fi
    if [ -n "$SOUND_PRE_TRIGGER" ]; then
        log "Buffer split: S#$SOUND_PRE_TRIGGER ($SOUND_PRE_TRIGGER pre / $((32 - SOUND_PRE_TRIGGER)) post segments)"
    fi
fi

if [ "$DEBUG_MODE" = true ]; then
    log "Debug mode enabled (verbose output)"
fi

if [ "$NO_CAMERA" = true ]; then
    log "Camera disabled"
else
    log "Camera enabled (Hough + ByteTrack)"
fi

$SERVER_CMD &
SERVER_PID=$!

# Wait for server to be ready
log "Waiting for server to start..."
for i in {1..30}; do
    if curl -s "http://$HOST:$PORT" > /dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

if ! curl -s "http://$HOST:$PORT" > /dev/null 2>&1; then
    error "Server failed to start"
    cleanup
    exit 1
fi

log "Server is running!"

# Launch browser in kiosk mode
log "Launching kiosk browser..."

KIOSK_URL="http://$HOST:$PORT"

# Try different browsers in order of preference
# DISPLAY=:0 allows running on Pi's display when SSHed in
# --password-store=basic disables the keyring unlock prompt
CHROME_FLAGS="--kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --password-store=basic"
if command -v chromium-browser &> /dev/null; then
    DISPLAY=:0 chromium-browser $CHROME_FLAGS "$KIOSK_URL" &
    BROWSER_PID=$!
elif command -v chromium &> /dev/null; then
    DISPLAY=:0 chromium $CHROME_FLAGS "$KIOSK_URL" &
    BROWSER_PID=$!
elif command -v google-chrome &> /dev/null; then
    DISPLAY=:0 google-chrome $CHROME_FLAGS "$KIOSK_URL" &
    BROWSER_PID=$!
elif command -v firefox &> /dev/null; then
    DISPLAY=:0 firefox --kiosk "$KIOSK_URL" &
    BROWSER_PID=$!
else
    warn "No supported browser found. Open $KIOSK_URL manually."
    warn "Supported browsers: chromium-browser, chromium, google-chrome, firefox"
fi

log "OpenFlight is running! Press Ctrl+C to stop."

# Wait for server process
wait $SERVER_PID
