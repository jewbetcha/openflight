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
NO_CAMERA=false  # Camera auto-enabled by default (uses Hough + ByteTrack)
MODE=""
TRIGGER=""
SOUND_PRE_TRIGGER=""

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
            MODE="$2"
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
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

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

if [ -n "$MODE" ]; then
    SERVER_CMD="$SERVER_CMD --mode $MODE"
fi

if [ -n "$TRIGGER" ]; then
    SERVER_CMD="$SERVER_CMD --trigger $TRIGGER"
fi

if [ -n "$SOUND_PRE_TRIGGER" ]; then
    SERVER_CMD="$SERVER_CMD --sound-pre-trigger $SOUND_PRE_TRIGGER"
fi

# Start the server
if [ "$MOCK_MODE" = true ]; then
    log "Starting OpenFlight server on port $PORT (MOCK MODE)..."
else
    log "Starting OpenFlight server on port $PORT..."
fi

if [ "$DEBUG_MODE" = true ]; then
    log "Debug mode enabled (verbose FFT/CFAR output)"
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

# Build the URL with optional mode parameter
KIOSK_URL="http://$HOST:$PORT"
if [ -n "$MODE" ]; then
    KIOSK_URL="$KIOSK_URL?mode=$MODE"
    log "Mode: $MODE"
fi

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
