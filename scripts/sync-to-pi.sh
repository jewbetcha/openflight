  #!/bin/bash
  PI_HOST="${PI_HOST:-pi@raspberrypi.local}"
  rsync -avz --delete \
    --exclude='.venv' --exclude='node_modules' --exclude='__pycache__' \
    --exclude='.git' --exclude='*.pyc' --exclude='ui/dist' --exclude='.pytest_cache' \
    --exclude='session_logs' --exclude='*.pkl' \
    ./ "$PI_HOST:~/openflight/"
  echo "Synced to $PI_HOST"


# usage: PI_HOST=coleman@golfmonitor.local ./scripts/sync-to-pi.sh