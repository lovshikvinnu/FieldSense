#!/usr/bin/env bash
#
# FieldSense AI — unattended boot entry point.
#
# Runs the whole offline stack on a physical Arduino UNO Q with no computer, no
# Wi-Fi, and no cloud attached. Invoked by deploy/fieldsense.service; also safe
# to run by hand:
#
#   ./scripts/boot_fieldsense.sh              # once, then exit
#   ./scripts/boot_fieldsense.sh --loop       # refresh forever
#
# What it does, in order:
#   1. Verify the interpreter can import the package (pure stdlib, no pip step).
#   2. Regenerate the dashboard and the panel summary from the pipeline.
#   3. Push a frame to the SPI panel, degrading to the browser-free renderer.
#   4. Optionally acquire live samples first, when FIELDSENSE_SOURCE is set to a
#      hardware source and a probe is attached.
#
# Every step logs and continues. A boot that half-works must still light the
# screen, because a dark panel in a field is indistinguishable from a dead board.
#
# Environment (all optional, all with working defaults):
#   FIELDSENSE_SOURCE=VIRTUAL|HARDWARE|BRIDGE|USB_PYSERIAL
#   FIELDSENSE_SENSOR_PORT=/dev/ttyUSB0
#   FIELDSENSE_POINTS=5                 live points to collect per cycle
#   FIELDSENSE_DATASET=field_test_live_hardware.json
#   FB_DEVICE=auto                      auto | /dev/fb0 | /dev/fb1
#   ROTATE=0                            0 | 90 | 180 | 270
#   REFRESH_SEC=300                     --loop interval
#   PYTHON=python3

set -uo pipefail   # deliberately NOT -e: a failed stage must not kill the boot

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python3}"
SOURCE="${FIELDSENSE_SOURCE:-VIRTUAL}"
POINTS="${FIELDSENSE_POINTS:-5}"
DATASET="${FIELDSENSE_DATASET:-field_test_live_hardware.json}"
FB_DEVICE="${FB_DEVICE:-auto}"
ROTATE="${ROTATE:-0}"
REFRESH_SEC="${REFRESH_SEC:-300}"

export PYTHONPATH="${PYTHONPATH:-$REPO_ROOT}"
export PYTHONUNBUFFERED=1

log() { printf '[fieldsense] %s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }

preflight() {
  log "repo        : $REPO_ROOT"
  log "python      : $("$PYTHON" -V 2>&1)"
  log "source      : $SOURCE"
  if ! "$PYTHON" -c "import fieldsense" 2>/dev/null; then
    log "FATAL: cannot import fieldsense from $REPO_ROOT"
    return 1
  fi
  # The runtime is pure standard library by design. Prove it here rather than
  # discovering a missing wheel on a board with no network to install one.
  "$PYTHON" - <<'PYEOF'
import importlib.util
third_party = []
for name in ("serial", "numpy", "pandas", "requests", "PIL"):
    if importlib.util.find_spec(name) is not None:
        third_party.append(name)
print("[fieldsense] stdlib-only  : yes (optional extras present: {})".format(
    ", ".join(third_party) or "none"))
PYEOF
  return 0
}

acquire() {
  case "$SOURCE" in
    HARDWARE|BRIDGE|USB_PYSERIAL)
      log "acquiring $POINTS live sample(s) from $SOURCE"
      # --no-interactive is mandatory here: systemd gives the unit no TTY, and
      # live_collector's operator prompt would block the boot forever.
      "$PYTHON" -m fieldsense.live_collector \
        --points "$POINTS" --out "$DATASET" --no-interactive --settle 2 \
        || { log "acquisition failed; continuing with the last dataset"; return 1; }
      log "running the spatial pipeline over $DATASET"
      "$PYTHON" run_spatial_test.py "$DATASET" --display off \
        || log "spatial pipeline failed; continuing"
      ;;
    *)
      log "source $SOURCE: skipping live acquisition"
      ;;
  esac
  return 0
}

render() {
  log "regenerating dashboard and panel summary"
  "$PYTHON" -m fieldsense.demo >/dev/null || log "demo failed; using the previous artifacts"
}

display() {
  log "pushing a frame to the panel (device=$FB_DEVICE rotate=$ROTATE)"
  # --device accepts 'auto' directly, so no conditional array expansion here:
  # bash 3.2 under `set -u` treats an empty array expansion as unbound.
  "$PYTHON" -m fieldsense.hardware.display_bridge \
    --target auto --rotate "$ROTATE" --device "$FB_DEVICE" \
    || log "display push failed; the panel keeps its last frame"
}

cycle() {
  acquire
  render
  display
}

preflight || exit 1

if [ "${1:-}" = "--loop" ]; then
  log "loop mode: every ${REFRESH_SEC}s"
  while true; do
    cycle
    sleep "$REFRESH_SEC"
  done
else
  cycle
  log "boot sequence complete"
fi
