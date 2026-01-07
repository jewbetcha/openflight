#!/bin/bash
# OpenLaunch Kiosk Launcher
# Double-click this or use the desktop shortcut to start the kiosk

cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Start the kiosk in fullscreen mode
python -m openlaunch.server --fullscreen

# Keep terminal open if there's an error
read -p "Press Enter to close..."
