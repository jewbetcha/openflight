#!/usr/bin/env bash
#
# Re-apply the OpenGolfSim "Developer API club sync" patch after an OGS update.
#
# OpenGolfSim's bundled Developer API (lib/launch/api.js) already speaks
# OpenConnect V1 on TCP 3111 and already replies with a `201 Player` block — but
# it hardcodes Club:"DR" and never wires in the real club from setClub(). This
# patch tracks the club from setClub() and sends the real (mapped) club, so
# OpenFlight's club picker follows OGS.
#
# It works because OGS's asar-integrity Electron fuse is OFF, so a modified
# app.asar loads without rehashing/re-signing. An OGS update overwrites app.asar,
# so re-run this after updating. The upstream fix (a ~3-line change to OGS) would
# make this unnecessary.
#
# Usage:  ./apply.sh [/Applications/OpenGolfSim.app]
#
set -euo pipefail

APP="${1:-/Applications/OpenGolfSim.app}"
RES="$APP/Contents/Resources"
ASAR="$RES/app.asar"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
STAMP="$(date +%Y%m%d-%H%M%S)"

[ -f "$ASAR" ] || { echo "app.asar not found at $ASAR"; exit 1; }

echo "1) Backing up app.asar -> $HOME/Downloads/app.asar.backup-$STAMP"
cp "$ASAR" "$HOME/Downloads/app.asar.backup-$STAMP"

echo "2) Extracting app.asar"
npx --yes @electron/asar extract "$ASAR" "$WORK/src"

echo "3) Applying the club-sync patch to lib/launch/api.js"
if patch -p1 -d "$WORK/src" < "$HERE/api.js.club-sync.patch"; then
  echo "   patch applied cleanly"
else
  echo "   !! patch did NOT apply cleanly (OGS likely changed api.js)."
  echo "   !! Compare api.patched-reference.js and hand-apply the 3 changes:"
  echo "      - add ogsClubToOpenConnect() mapper"
  echo "      - override setClub() to store this.currentClub + push a 201"
  echo "      - in the existing 201, send Club: this.currentClub (not \"DR\")"
  exit 1
fi

echo "4) Repacking (keeping native .node modules unpacked)"
npx --yes @electron/asar pack "$WORK/src" "$WORK/app.asar.new" --unpack "**/*.node"

# sanity: same native unpack set as the shipped app
ORIG="$(cd "$RES/app.asar.unpacked" && find . -type f | sort)"
NEW="$(cd "$WORK/app.asar.new.unpacked" && find . -type f | sort)"
[ "$ORIG" = "$NEW" ] || { echo "!! unpack set changed — aborting"; exit 1; }
echo "   unpack set matches the shipped app ✓"

echo "5) Installing patched app.asar"
if cp "$WORK/app.asar.new" "$RES/app.asar.patched-tmp" 2>/dev/null && \
   mv "$RES/app.asar.patched-tmp" "$ASAR" 2>/dev/null; then
  echo "   installed ✓"
else
  cp "$WORK/app.asar.new" "$HOME/Downloads/app.asar.clubsync-patched"
  echo "   !! Could not write into the app bundle (macOS App Management protection)."
  echo "   !! Patched asar saved to ~/Downloads/app.asar.clubsync-patched — install it via Finder:"
  echo "      /Applications -> right-click OpenGolfSim -> Show Package Contents ->"
  echo "      Contents/Resources -> replace app.asar with that file (authenticate)."
fi

echo "Done. Fully quit and relaunch OpenGolfSim, then select the Developer API device."
rm -rf "$WORK"
