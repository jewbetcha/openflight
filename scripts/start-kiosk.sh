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
TRACKMAN_TEST=false
SESSION_LOCATION=""
DRY_RUN=false
# Rolling buffer mode is the only mode (streaming mode removed)
TRIGGER="sound"  # Default: hardware sound trigger (SEN-14262 → HOST_INT)
SOUND_PRE_TRIGGER=""
BUFFER_SPLIT=""
KLD7=false
KLD7_PORT=""
KLD7_ANGLE_OFFSET=""
KLD7_HORIZONTAL=false
KLD7_HORIZONTAL_PORT=""
KLD7_HORIZONTAL_OFFSET=""
KLD7_GEOMETRY=false
KLD7_VERTICAL_ESTIMATOR=""
KLD7_MOUNT_TILT=""
KLD7_BALL_DISTANCE=""
EXPERIMENTAL_KLD7_RAW_RADC_LOGGING=false
EXPERIMENTAL_KLD7_RADC_TUNING=false
EXPERIMENTAL_KLD7_SPEED_TOLERANCE=""
EXPERIMENTAL_KLD7_CENTROID_FLOOR=""
EXPERIMENTAL_KLD7_OPS_BIN_TOL=""
EXPERIMENTAL_KLD7_OPS_BIN_PENALTY=""
EXPERIMENTAL_KLD7_OPS_ANCHORED_MIN_SNR=""
EXPERIMENTAL_KLD7_VERTICAL_IMPACT_ENERGY=""
EXPERIMENTAL_KLD7_HORIZONTAL_IMPACT_ENERGY=""
EXPERIMENTAL_KLD7_HORIZONTAL_RETRY_IMPACT_ENERGY=""
EXPERIMENTAL_KLD7_HORIZONTAL_ANGLE_LIMIT=""
BALLISTICS=false
SIM=false
CALCULATED_SPIN=false
BALL_SPEED_COSINE=false

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
        --trackman-test)
            TRACKMAN_TEST=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --session-location|-l)
            SESSION_LOCATION="$2"
            shift 2
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
        --kld7-geometry)
            KLD7_GEOMETRY=true
            shift
            ;;
        --kld7-port)
            KLD7_PORT="$2"
            shift 2
            ;;
        --kld7-angle-offset)
            KLD7_ANGLE_OFFSET="$2"
            shift 2
            ;;
        --kld7-vertical-estimator)
            KLD7_VERTICAL_ESTIMATOR="$2"
            shift 2
            ;;
        --kld7-mount-tilt)
            KLD7_MOUNT_TILT="$2"
            shift 2
            ;;
        --kld7-ball-distance)
            KLD7_BALL_DISTANCE="$2"
            shift 2
            ;;
        --kld7-horizontal)
            KLD7_HORIZONTAL=true
            shift
            ;;
        --kld7-horizontal-port)
            KLD7_HORIZONTAL_PORT="$2"
            shift 2
            ;;
        --kld7-horizontal-offset)
            KLD7_HORIZONTAL_OFFSET="$2"
            shift 2
            ;;
        --experimental-kld7-raw-radc-logging)
            EXPERIMENTAL_KLD7_RAW_RADC_LOGGING=true
            shift
            ;;
        --experimental-kld7-radc-tuning)
            EXPERIMENTAL_KLD7_RADC_TUNING=true
            shift
            ;;
        --experimental-kld7-speed-tolerance)
            EXPERIMENTAL_KLD7_SPEED_TOLERANCE="$2"
            shift 2
            ;;
        --experimental-kld7-centroid-floor)
            EXPERIMENTAL_KLD7_CENTROID_FLOOR="$2"
            shift 2
            ;;
        --experimental-kld7-spectrum-source)
            EXPERIMENTAL_KLD7_SPECTRUM_SOURCE="$2"
            shift 2
            ;;
        --experimental-kld7-ops-bin-tol)
            EXPERIMENTAL_KLD7_OPS_BIN_TOL="$2"
            shift 2
            ;;
        --experimental-kld7-ops-bin-penalty)
            EXPERIMENTAL_KLD7_OPS_BIN_PENALTY="$2"
            shift 2
            ;;
        --experimental-kld7-ops-anchored-min-snr)
            EXPERIMENTAL_KLD7_OPS_ANCHORED_MIN_SNR="$2"
            shift 2
            ;;
        --experimental-kld7-vertical-impact-energy)
            EXPERIMENTAL_KLD7_VERTICAL_IMPACT_ENERGY="$2"
            shift 2
            ;;
        --experimental-kld7-horizontal-impact-energy)
            EXPERIMENTAL_KLD7_HORIZONTAL_IMPACT_ENERGY="$2"
            shift 2
            ;;
        --experimental-kld7-horizontal-retry-impact-energy)
            EXPERIMENTAL_KLD7_HORIZONTAL_RETRY_IMPACT_ENERGY="$2"
            shift 2
            ;;
        --experimental-kld7-horizontal-angle-limit)
            EXPERIMENTAL_KLD7_HORIZONTAL_ANGLE_LIMIT="$2"
            shift 2
            ;;
        --ballistics)
            BALLISTICS=true
            shift
            ;;
        --sim)
            SIM=true
            shift
            ;;
        --calculated-spin)
            CALCULATED_SPIN=true
            shift
            ;;
        --ball-speed-cosine-correction)
            BALL_SPEED_COSINE=true
            shift
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

if [ "$TRACKMAN_TEST" = true ]; then
    KLD7=true
    KLD7_GEOMETRY=true
    KLD7_HORIZONTAL=true
    EXPERIMENTAL_KLD7_RAW_RADC_LOGGING=true
    SESSION_LOCATION="${SESSION_LOCATION:-trackman}"
fi

if [ "$KLD7_GEOMETRY" = true ]; then
    KLD7=true
    KLD7_HORIZONTAL=true
    KLD7_VERTICAL_ESTIMATOR="${KLD7_VERTICAL_ESTIMATOR:-geometry}"
    KLD7_MOUNT_TILT="${KLD7_MOUNT_TILT:-10}"
    KLD7_BALL_DISTANCE="${KLD7_BALL_DISTANCE:-5}"
    KLD7_ANGLE_OFFSET="${KLD7_ANGLE_OFFSET:-2.5}"
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
    # Chromium forks child processes that survive kill — clean them all
    pkill -f "chromium.*--kiosk" 2>/dev/null || true
    pkill -f "chrome.*--kiosk" 2>/dev/null || true
    exit 0
}

configure_kld7_latency() {
    local setup_script="$PROJECT_DIR/scripts/setup/setup_kld7_latency.sh"

    if [ "$KLD7" != true ] && [ "$KLD7_HORIZONTAL" != true ] && [ ! -e /dev/kld7_vertical ] && [ ! -e /dev/kld7_horizontal ]; then
        return 0
    fi

    if [ "$(uname -s)" != "Linux" ]; then
        warn "Skipping K-LD7 FTDI latency setup (Linux-only)"
        return 0
    fi

    if [ ! -x "$setup_script" ]; then
        warn "Skipping K-LD7 FTDI latency setup (missing $setup_script)"
        return 0
    fi

    log "Applying K-LD7 FTDI latency setup..."
    if [ "$(id -u)" -eq 0 ]; then
        if "$setup_script" --latency 1; then
            log "K-LD7 FTDI latency setup complete"
        else
            warn "K-LD7 FTDI latency setup failed; continuing startup"
        fi
    elif command -v sudo >/dev/null 2>&1; then
        if sudo -n "$setup_script" --latency 1; then
            log "K-LD7 FTDI latency setup complete"
        else
            warn "K-LD7 FTDI latency setup failed; continuing startup"
            warn "  Run manually if needed: sudo scripts/setup/setup_kld7_latency.sh"
        fi
    else
        warn "Skipping K-LD7 FTDI latency setup (sudo not available)"
    fi
}

trap cleanup SIGINT SIGTERM

cd "$PROJECT_DIR"

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

if [ "$BALLISTICS" = true ]; then
    SERVER_CMD="$SERVER_CMD --ballistics"
fi

# Simulator connectors: off unless --sim; targets come from config/sim.json
if [ "$SIM" = true ]; then
    SERVER_CMD="$SERVER_CMD --sim"
fi

if [ "$CALCULATED_SPIN" = true ]; then
    SERVER_CMD="$SERVER_CMD --calculated-spin"
fi

if [ "$BALL_SPEED_COSINE" = true ]; then
    SERVER_CMD="$SERVER_CMD --ball-speed-cosine-correction"
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

if [ -n "$SESSION_LOCATION" ]; then
    SERVER_CMD="$SERVER_CMD --session-location $SESSION_LOCATION"
fi

if [ "$EXPERIMENTAL_KLD7_RAW_RADC_LOGGING" = true ]; then
    SERVER_CMD="$SERVER_CMD --experimental-kld7-raw-radc-logging"
fi

if [ "$EXPERIMENTAL_KLD7_RADC_TUNING" = true ]; then
    SERVER_CMD="$SERVER_CMD --experimental-kld7-radc-tuning"

    if [ -n "$EXPERIMENTAL_KLD7_SPEED_TOLERANCE" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-speed-tolerance $EXPERIMENTAL_KLD7_SPEED_TOLERANCE"
    fi

    if [ -n "$EXPERIMENTAL_KLD7_CENTROID_FLOOR" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-centroid-floor $EXPERIMENTAL_KLD7_CENTROID_FLOOR"
    fi

    if [ -n "$EXPERIMENTAL_KLD7_SPECTRUM_SOURCE" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-spectrum-source $EXPERIMENTAL_KLD7_SPECTRUM_SOURCE"
    fi

    if [ -n "$EXPERIMENTAL_KLD7_OPS_BIN_TOL" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-ops-bin-tol $EXPERIMENTAL_KLD7_OPS_BIN_TOL"
    fi

    if [ -n "$EXPERIMENTAL_KLD7_OPS_BIN_PENALTY" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-ops-bin-penalty $EXPERIMENTAL_KLD7_OPS_BIN_PENALTY"
    fi

    if [ -n "$EXPERIMENTAL_KLD7_OPS_ANCHORED_MIN_SNR" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-ops-anchored-min-snr $EXPERIMENTAL_KLD7_OPS_ANCHORED_MIN_SNR"
    fi

    if [ -n "$EXPERIMENTAL_KLD7_VERTICAL_IMPACT_ENERGY" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-vertical-impact-energy $EXPERIMENTAL_KLD7_VERTICAL_IMPACT_ENERGY"
    fi

    if [ -n "$EXPERIMENTAL_KLD7_HORIZONTAL_IMPACT_ENERGY" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-horizontal-impact-energy $EXPERIMENTAL_KLD7_HORIZONTAL_IMPACT_ENERGY"
    fi

    if [ -n "$EXPERIMENTAL_KLD7_HORIZONTAL_RETRY_IMPACT_ENERGY" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-horizontal-retry-impact-energy $EXPERIMENTAL_KLD7_HORIZONTAL_RETRY_IMPACT_ENERGY"
    fi

    if [ -n "$EXPERIMENTAL_KLD7_HORIZONTAL_ANGLE_LIMIT" ]; then
        SERVER_CMD="$SERVER_CMD --experimental-kld7-horizontal-angle-limit $EXPERIMENTAL_KLD7_HORIZONTAL_ANGLE_LIMIT"
    fi
elif [ -n "$EXPERIMENTAL_KLD7_SPEED_TOLERANCE$EXPERIMENTAL_KLD7_CENTROID_FLOOR$EXPERIMENTAL_KLD7_SPECTRUM_SOURCE$EXPERIMENTAL_KLD7_OPS_BIN_TOL$EXPERIMENTAL_KLD7_OPS_BIN_PENALTY$EXPERIMENTAL_KLD7_OPS_ANCHORED_MIN_SNR$EXPERIMENTAL_KLD7_VERTICAL_IMPACT_ENERGY$EXPERIMENTAL_KLD7_HORIZONTAL_IMPACT_ENERGY$EXPERIMENTAL_KLD7_HORIZONTAL_RETRY_IMPACT_ENERGY$EXPERIMENTAL_KLD7_HORIZONTAL_ANGLE_LIMIT" ]; then
    warn "Ignoring experimental K-LD7 RADC tuning values without --experimental-kld7-radc-tuning"
fi

# K-LD7 radar defaults when --kld7 is enabled
if [ "$KLD7" = true ]; then
    SERVER_CMD="$SERVER_CMD --kld7"
    SERVER_CMD="$SERVER_CMD --kld7-port ${KLD7_PORT:-/dev/kld7_vertical}"
    SERVER_CMD="$SERVER_CMD --kld7-angle-offset ${KLD7_ANGLE_OFFSET:-8}"
    # Geometry estimator config is forwarded only when set explicitly or via
    # --kld7-geometry/--trackman-test. Plain --kld7 keeps the historical kiosk
    # defaults unless the caller opts into the geometry field preset.
    [ -n "$KLD7_VERTICAL_ESTIMATOR" ] && SERVER_CMD="$SERVER_CMD --kld7-vertical-estimator $KLD7_VERTICAL_ESTIMATOR"
    [ -n "$KLD7_MOUNT_TILT" ] && SERVER_CMD="$SERVER_CMD --kld7-mount-tilt $KLD7_MOUNT_TILT"
    [ -n "$KLD7_BALL_DISTANCE" ] && SERVER_CMD="$SERVER_CMD --kld7-ball-distance $KLD7_BALL_DISTANCE"
    # Auto-enable horizontal if symlink exists and not explicitly disabled
    if [ "$KLD7_HORIZONTAL" != true ] && [ -e /dev/kld7_horizontal ]; then
        KLD7_HORIZONTAL=true
    fi
    if [ "$KLD7_HORIZONTAL" = true ]; then
        SERVER_CMD="$SERVER_CMD --kld7-horizontal"
        SERVER_CMD="$SERVER_CMD --kld7-horizontal-port ${KLD7_HORIZONTAL_PORT:-/dev/kld7_horizontal}"
        SERVER_CMD="$SERVER_CMD --kld7-horizontal-offset ${KLD7_HORIZONTAL_OFFSET:-0}"
    fi
fi

if [ "$DRY_RUN" = true ]; then
    echo "$SERVER_CMD"
    exit 0
fi

# Ensure the environment is in sync (uv recreates/repairs .venv as needed,
# so a moved project dir self-heals instead of failing with "command not found")
if ! command -v uv >/dev/null 2>&1; then
    error "uv not found. Install it: https://docs.astral.sh/uv/"
    exit 1
fi
uv sync --quiet

configure_kld7_latency

# Check if UI is built
if [ ! -d "ui/dist" ]; then
    warn "UI not built. Building now..."
    cd ui
    npm install
    npm run build
    cd ..
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
        warn "Alloy installed but no credentials file found (run: sudo scripts/setup/setup_alloy.sh)"
    fi
else
    warn "Grafana Alloy not installed — session logs will only be saved locally"
    warn "  Install with: sudo scripts/setup/setup_alloy.sh"
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

if [ "$TRACKMAN_TEST" = true ]; then
    log "TrackMan test mode enabled (dual K-LD7, raw RADC logging, location: $SESSION_LOCATION)"
fi

if [ "$NO_CAMERA" = true ]; then
    log "Camera disabled"
else
    log "Camera enabled (Hough + ByteTrack)"
fi

if [ "$BALLISTICS" = true ]; then
    log "Ballistic carry model enabled (simulator + drag/Magnus)"
else
    log "Ballistic carry model disabled (using legacy table)"
fi

uv run $SERVER_CMD &
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

# Wait for server process — exits when server stops (Ctrl+C or UI shutdown)
wait $SERVER_PID
cleanup
