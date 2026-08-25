#!/usr/bin/env bash
#
# FieldSense AI — standalone field node.
#
# One command, run directly on the board, that does everything FIELD_RUN.md
# describes by hand:
#
#     arduino@uno:~$ ./scripts/run_standalone_node.sh
#
#   1. Make sure the App Lab app (user:unified_v1) is up — it owns both the
#      GPS gateway and the MCU monitor proxy the panel push needs.
#   2. Discover the gateway container address, which changes on every rebuild.
#   3. Optionally wait for a real satellite fix before recording anything.
#   4. Collect N probe samples, interpolate, render the dashboard, and push
#      values to the 2.8" TFT over the router bridge.
#   5. Repeat forever in --loop mode.
#
# WHY --display bridge AND NOT A FRAMEBUFFER
# ------------------------------------------
# The QRB2210 routes no SPI to the external headers, so no /dev/fbN can ever
# exist for this panel. `--display auto` finds nothing and silently leaves the
# screen dark. `bridge` sends a compact value record to the STM32 over the
# router monitor proxy, which is the only path that reaches the panel here.
#
# WHY IT WAITS FOR A FIX BY DEFAULT
# ---------------------------------
# The collector runs happily with no lock and records every point at
# 0.000000, 0.000000. Nothing errors, five samples are captured, and the map is
# meaningless. That has already happened once. A field node that records
# garbage is worse than one that records nothing, so a cycle without a fix is
# skipped and retried rather than written. Set REQUIRE_GPS_FIX=0 for a bench
# run where position does not matter.
#
# Environment (all optional):
#   POINTS=5                    samples per cycle
#   REQUIRE_GPS_FIX=1           1 = skip a cycle with no lock, 0 = record anyway
#   GPS_FIX_TIMEOUT=300         seconds to wait for FIX_OK
#   GATEWAY_HOST=auto           auto-discovered, or set explicitly
#   GATEWAY_PORT=9876
#   GATEWAY_WAIT_SECONDS=180     wait for the gateway before restarting
#   MCU_PORT=127.0.0.1:7500     router monitor proxy for the panel push
#   SENSOR_PORT=/dev/ttyUSB0    USB-RS485 adapter
#   APP_NAME=user:unified_v1
#   DATASET=field_test_live_hardware.json
#   OUTPUT_DIR=artifacts
#   INTERVAL=900                --loop seconds between cycles
#   INTERACTIVE=0               1 = wait for Enter at each point
#   SIMULATE=0                  1 = virtual sensor, output stamped SIMULATED
#   LOG_FILE=                   also append output here
#
set -uo pipefail   # deliberately not -e: one bad cycle must not kill the node

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python3}"
POINTS="${POINTS:-5}"
REQUIRE_GPS_FIX="${REQUIRE_GPS_FIX:-1}"
GPS_FIX_TIMEOUT="${GPS_FIX_TIMEOUT:-300}"
GATEWAY_HOST="${GATEWAY_HOST:-auto}"
GATEWAY_PORT="${GATEWAY_PORT:-9876}"
GATEWAY_WAIT_SECONDS="${GATEWAY_WAIT_SECONDS:-180}"
MCU_PORT="${MCU_PORT:-127.0.0.1:7500}"
SENSOR_PORT="${SENSOR_PORT:-/dev/ttyUSB0}"
APP_NAME="${APP_NAME:-user:unified_v1}"
DATASET="${DATASET:-field_test_live_hardware.json}"
OUTPUT_DIR="${OUTPUT_DIR:-artifacts}"
INTERVAL="${INTERVAL:-900}"
INTERACTIVE="${INTERACTIVE:-0}"
SIMULATE="${SIMULATE:-0}"
LOG_FILE="${LOG_FILE:-}"

LOOP=0
for arg in "$@"; do
  case "$arg" in
    --loop)     LOOP=1 ;;
    --once)     LOOP=0 ;;
    --simulate) SIMULATE=1 ;;
    -h|--help)  sed -n '2,60p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $arg (try --help)" >&2; exit 2 ;;
  esac
done

export PYTHONPATH="${PYTHONPATH:-$REPO_ROOT}"
export PYTHONUNBUFFERED=1

log() {
  local line="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$line"
  [ -n "$LOG_FILE" ] && echo "$line" >> "$LOG_FILE"
  return 0
}

# ---------------------------------------------------------------- App Lab app

app_cli() { command -v arduino-app-cli >/dev/null 2>&1; }

ensure_app_running() {
  if ! app_cli; then
    log "arduino-app-cli not found; assuming $APP_NAME is already running"
    return 0
  fi
  if gateway_reachable "$1"; then
    return 0
  fi
  # WHY WAITING COMES BEFORE RESTARTING
  #
  # Starting an App Lab app FLASHES THE MCU - its log carries openocd bank
  # writes and `Progress[sketch updated]`. On a cold boot this node can be
  # running before App Lab has finished that flash, and a restart issued in that
  # window puts a second openocd on the same SWD lines, which fails with
  # `Error requesting gpio line swdio` and needs `sudo killall -9 openocd` to
  # clear. An unattended field node cannot do that for itself, so a slow start
  # must never be mistaken for a broken one. Waiting is also strictly cheaper: a
  # restart costs a flash cycle, waiting costs seconds.
  log "gateway not up yet; waiting up to ${GATEWAY_WAIT_SECONDS}s for $APP_NAME"
  if wait_for_gateway; then
    log "gateway appeared on its own; no restart needed"
    return 0
  fi

  log "gateway still unreachable after ${GATEWAY_WAIT_SECONDS}s; restarting $APP_NAME"
  log "note: this reflashes the MCU, so the panel will reset"
  arduino-app-cli app restart "$APP_NAME" >/dev/null 2>&1 \
    || log "could not restart $APP_NAME (continuing anyway)"
  sleep 15
}

# Poll until the gateway answers or the budget runs out.
#
# The container address is re-discovered on every pass rather than taken as an
# argument: at boot the container may not exist yet, so its address is not
# knowable before the wait, only during it.
wait_for_gateway() {
  local deadline=$(( SECONDS + GATEWAY_WAIT_SECONDS ))
  local host
  while [ "$SECONDS" -lt "$deadline" ]; do
    host="$(discover_gateway)"
    if gateway_reachable "$host"; then
      return 0
    fi
    sleep 5
  done
  return 1
}

discover_gateway() {
  if [ "$GATEWAY_HOST" != "auto" ]; then
    echo "$GATEWAY_HOST"; return 0
  fi
  # The App Lab container address changes on every rebuild, which is the step
  # most often missed by hand.
  local container="${APP_NAME#user:}-main-1"
  local found
  found="$(docker exec "$container" hostname -i 2>/dev/null | awk '{print $1}')"
  if [ -n "$found" ]; then echo "$found"; return 0; fi
  echo "127.0.0.1"
}

gateway_reachable() {
  "$PYTHON" - "$1" "$GATEWAY_PORT" <<'PY' 2>/dev/null
import socket, sys
try:
    with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=2):
        sys.exit(0)
except Exception:
    sys.exit(1)
PY
}

# ---------------------------------------------------------------- GPS gate

wait_for_fix() {
  local host="$1" deadline=$(( SECONDS + GPS_FIX_TIMEOUT ))
  log "waiting up to ${GPS_FIX_TIMEOUT}s for a satellite fix at ${host}:${GATEWAY_PORT}"
  while [ "$SECONDS" -lt "$deadline" ]; do
    local payload
    payload="$("$PYTHON" - "$host" "$GATEWAY_PORT" <<'PY' 2>/dev/null
import socket, sys
try:
    with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=3) as s:
        sys.stdout.write(s.recv(256).decode("utf-8", "ignore").strip())
except Exception:
    pass
PY
)"
    case "$payload" in
      FIX_OK*) log "fix acquired: ${payload%%,Sats*} ${payload#*Sats}"; return 0 ;;
      NO_FIX*) : ;;
      "")      log "gateway silent; is $APP_NAME running?" ;;
    esac
    sleep 10
  done
  return 1
}

# ---------------------------------------------------------------- one cycle

run_cycle() {
  local host; host="$(discover_gateway)"
  log "gateway host: $host:$GATEWAY_PORT   probe: $SENSOR_PORT   panel: $MCU_PORT"

  ensure_app_running "$host"
  host="$(discover_gateway)"

  if [ "$SIMULATE" != "1" ] && [ "$REQUIRE_GPS_FIX" = "1" ]; then
    if ! wait_for_fix "$host"; then
      log "no satellite fix within ${GPS_FIX_TIMEOUT}s — skipping this cycle"
      log "recording without a fix would write every point at 0.000000, 0.000000"
      return 1
    fi
  fi

  local args=(
    -m fieldsense.v1_runner
    --samples "$POINTS"
    --out "$DATASET"
    --port "$SENSOR_PORT"
    --output-dir "$OUTPUT_DIR"
    --display bridge
    --mcu-port "$MCU_PORT"
  )
  [ "$INTERACTIVE" = "1" ] || args+=(--no-interactive)
  [ "$SIMULATE" = "1" ]    && args+=(--simulate)

  FIELDSENSE_SOURCE=HARDWARE \
  FIELDSENSE_SENSOR_PORT="$SENSOR_PORT" \
  FIELDSENSE_GPS_GATEWAY_HOST="$host" \
  FIELDSENSE_GPS_GATEWAY_PORT="$GATEWAY_PORT" \
  "$PYTHON" "${args[@]}"
  local rc=$?

  if [ "$rc" -eq 0 ]; then
    log "cycle complete: $DATASET + $OUTPUT_DIR/field_test_map.html, panel updated"
  else
    log "cycle failed (exit $rc); the panel keeps its last frame"
  fi
  return "$rc"
}

# ---------------------------------------------------------------- main

log "FieldSense standalone node starting in $REPO_ROOT"
log "points=$POINTS require_fix=$REQUIRE_GPS_FIX simulate=$SIMULATE loop=$LOOP"

if ! "$PYTHON" -c "import fieldsense" >/dev/null 2>&1; then
  log "FATAL: cannot import fieldsense from $REPO_ROOT"
  exit 1
fi

if [ "$LOOP" = "1" ]; then
  log "loop mode: a cycle every ${INTERVAL}s (Ctrl-C to stop)"
  while true; do
    run_cycle
    log "sleeping ${INTERVAL}s"
    sleep "$INTERVAL"
  done
else
  run_cycle
  exit $?
fi
