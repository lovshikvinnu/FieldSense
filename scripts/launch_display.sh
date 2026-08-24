#!/usr/bin/env bash
#
# FieldSense AI - launch the dashboard onto the 2.8" SPI panel.
#
#   ./scripts/launch_display.sh                 # auto-detect and go
#   ./scripts/launch_display.sh probe           # report environment, change nothing
#   ./scripts/launch_display.sh fb              # push a frame to the framebuffer
#   ./scripts/launch_display.sh kiosk           # full-screen browser
#   ./scripts/launch_display.sh png             # save a 240x320 preview
#   ./scripts/launch_display.sh watch           # refresh the panel every REFRESH_SEC
#
# Environment overrides:
#   FB_DEVICE=auto         framebuffer device (auto detects /dev/fb1 then /dev/fb0)
#   ROTATE=0               0 | 90 | 180 | 270 (clockwise)
#   WIDTH=240 HEIGHT=320   panel geometry
#   BYTEORDER=little       little for /dev/fbN, big for a raw SPI stream
#   BROWSER=/usr/bin/chromium
#   REGENERATE=1           re-run the pipeline before displaying
#   REFRESH_SEC=30         watch-mode interval
#
set -euo pipefail

TARGET="${1:-auto}"
# 'auto' rather than a hardcoded /dev/fb1: on a board where the SPI panel is the
# only framebuffer it enumerates as /dev/fb0, and the old default wrote to a
# device that did not exist there.
FB_DEVICE="${FB_DEVICE:-auto}"
ROTATE="${ROTATE:-0}"
WIDTH="${WIDTH:-240}"
HEIGHT="${HEIGHT:-320}"
BYTEORDER="${BYTEORDER:-little}"
REGENERATE="${REGENERATE:-1}"
REFRESH_SEC="${REFRESH_SEC:-30}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python3}"
HTML="${HTML:-artifacts/fieldsense_competition_demo.html}"

bridge_args=(
  --html "$HTML"
  --device "$FB_DEVICE"
  --width "$WIDTH"
  --height "$HEIGHT"
  --rotate "$ROTATE"
  --byteorder "$BYTEORDER"
)
[ -n "${BROWSER:-}" ] && bridge_args+=(--browser "$BROWSER")

run_bridge() {
  "$PYTHON" -m fieldsense.hardware.display_bridge --target "$1" "${bridge_args[@]}"
}

regenerate() {
  if [ "$REGENERATE" = "1" ]; then
    echo "==> Regenerating dashboard"
    "$PYTHON" -m fieldsense.demo >/dev/null
  fi
}

case "$TARGET" in
  probe)
    "$PYTHON" -m fieldsense.hardware.display_bridge --target probe
    ;;

  watch)
    echo "==> Watch mode: refreshing $FB_DEVICE every ${REFRESH_SEC}s (Ctrl-C to stop)"
    while true; do
      regenerate
      run_bridge fb || echo "    (frame failed, retrying next cycle)"
      sleep "$REFRESH_SEC"
    done
    ;;

  auto|fb|png|kiosk)
    regenerate
    echo "==> Display target: $TARGET"
    run_bridge "$TARGET"
    ;;

  *)
    echo "usage: $0 [auto|probe|fb|png|kiosk|watch]" >&2
    exit 2
    ;;
esac
