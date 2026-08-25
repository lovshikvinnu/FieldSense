#!/usr/bin/env bash
#
# FieldSense AI — field session launcher.
#
# The command the boot service runs, and the one to run by hand on the board:
#
#     arduino@uno:~$ ./scripts/run_field_session.sh
#
# It brings up the multi-sample workflow described in docs/FIELD_SESSION.md:
# power on, wait for App Lab, wait for a satellite fix, then hand the unit to
# the operator. From there the panel is the interface — press START, walk,
# press START — and no laptop, SSH session, or network is involved.
#
# HOW THIS DIFFERS FROM run_standalone_node.sh
# --------------------------------------------
# That script runs a whole V1 cycle unattended: it collects N points back to
# back with no operator input and no way to tell which sample is which. It is
# still the right thing for a fixed installation.
#
# This script runs a FIELD SESSION. The operator decides when each sample
# begins, every sample is stored under its own index the moment it is taken,
# and the session survives a power cut. That is the difference between a logger
# and an instrument somebody carries.
#
# NO NETWORK IS REQUIRED, AND NONE IS USED
# ----------------------------------------
# The GPS gateway is an App Lab container on this board, reached at its own
# address on the docker bridge. The panel link is arduino-router's monitor
# proxy on 127.0.0.1:7500. The probe is a tty. The SLM weights are a file. The
# unit is expected to run with the radios off, and this script never contacts
# anything that is not on the board.
#
# Environment (all optional):
#   SAMPLES=5                   samples in a session
#   TRIGGER=any                 any | button | mcu | enter | auto
#                               'any' watches every control the unit has: the
#                               board's own VOL+/VOL- keys and the panel's touch
#                               target / a switch on D5.
#   REQUIRE_GPS_FIX=1           1 = wait for a lock before arming, 0 = arm anyway
#   GPS_FIX_TIMEOUT=300         seconds to wait for FIX_OK
#   GATEWAY_HOST=auto           auto-discovered, or set explicitly
#   GATEWAY_PORT=9876
#   GATEWAY_WAIT_SECONDS=180    wait for App Lab's gateway before restarting it
#   MCU_PORT=127.0.0.1:7500     router monitor proxy for the panel
#   SENSOR_PORT=/dev/ttyUSB0    USB-RS485 adapter
#   APP_NAME=user:unified_v1
#   SESSION_ROOT=artifacts/sessions
#   DATASET=field_test_live_hardware.json
#   OUTPUT_DIR=artifacts
#   FIELD_NAME=                 label shown on the panel
#   RESUME=                     session id to continue after a power cut
#   SIMULATE=0                  1 = virtual sensor, output stamped SIMULATED
#   LOOP=0                      1 = start a new session after each one finishes
#   LOG_FILE=                   also append output here
#
set -uo pipefail   # deliberately not -e: one bad session must not kill the node

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python3}"
SAMPLES="${SAMPLES:-5}"
TRIGGER="${TRIGGER:-any}"
REQUIRE_GPS_FIX="${REQUIRE_GPS_FIX:-1}"
GPS_FIX_TIMEOUT="${GPS_FIX_TIMEOUT:-300}"
GATEWAY_HOST="${GATEWAY_HOST:-auto}"
GATEWAY_PORT="${GATEWAY_PORT:-9876}"
GATEWAY_WAIT_SECONDS="${GATEWAY_WAIT_SECONDS:-180}"
MCU_PORT="${MCU_PORT:-127.0.0.1:7500}"
SENSOR_PORT="${SENSOR_PORT:-/dev/ttyUSB0}"
APP_NAME="${APP_NAME:-user:unified_v1}"
SESSION_ROOT="${SESSION_ROOT:-artifacts/sessions}"
DATASET="${DATASET:-field_test_live_hardware.json}"
OUTPUT_DIR="${OUTPUT_DIR:-artifacts}"
FIELD_NAME="${FIELD_NAME:-}"
RESUME="${RESUME:-}"
SIMULATE="${SIMULATE:-0}"
LOOP="${LOOP:-0}"
LOG_FILE="${LOG_FILE:-}"

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

# Poll until the gateway answers or the budget runs out. The address is
# re-discovered on every pass rather than taken as an argument: at boot the
# container may not exist yet, so its address is not knowable before the wait.
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
  # clear. An unattended field unit cannot do that for itself, so a slow start
  # must never be mistaken for a broken one.
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

# ---------------------------------------------------------------- GPS gate

# Wait for a lock BEFORE arming the panel.
#
# The workflow retries a sample taken without one, so a session is never
# corrupted by starting early - but an operator who presses START and is told
# to press again has been sent to walk for nothing. Waiting here means the
# panel says READY only when a press will actually produce a located sample.
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

# ---------------------------------------------------------------- one session

run_session() {
  local host; host="$(discover_gateway)"
  log "gateway: $host:$GATEWAY_PORT   probe: $SENSOR_PORT   panel: $MCU_PORT"

  ensure_app_running "$host"
  host="$(discover_gateway)"

  if [ "$SIMULATE" != "1" ] && [ "$REQUIRE_GPS_FIX" = "1" ]; then
    if ! wait_for_fix "$host"; then
      log "no satellite fix within ${GPS_FIX_TIMEOUT}s"
      log "arming anyway: the workflow retries a sample taken without a fix and"
      log "stores it marked rather than silently placing it at 0.000000, 0.000000"
    fi
  fi

  local args=(
    -m fieldsense.field_node
    --samples "$SAMPLES"
    --trigger "$TRIGGER"
    --port "$SENSOR_PORT"
    --panel "$MCU_PORT"
    --session-root "$SESSION_ROOT"
    --output-dir "$OUTPUT_DIR"
    --dataset "$DATASET"
  )
  [ -n "$FIELD_NAME" ] && args+=(--field-name "$FIELD_NAME")
  [ -n "$RESUME" ]     && args+=(--resume "$RESUME")
  [ "$SIMULATE" = "1" ] && args+=(--simulate)

  FIELDSENSE_SOURCE=HARDWARE \
  FIELDSENSE_SENSOR_PORT="$SENSOR_PORT" \
  FIELDSENSE_GPS_GATEWAY_HOST="$host" \
  FIELDSENSE_GPS_GATEWAY_PORT="$GATEWAY_PORT" \
  "$PYTHON" "${args[@]}"
  local rc=$?

  if [ "$rc" -eq 0 ]; then
    log "session complete; records under $SESSION_ROOT"
  else
    log "session ended with exit $rc; the session directory still holds every "
    log "sample that was taken - nothing is discarded on a bad exit"
  fi
  # RESUME applies to one session only. Carrying it into the next pass of
  # --loop would append tomorrow's samples to yesterday's session.
  RESUME=""
  return "$rc"
}

# ---------------------------------------------------------------- main

log "FieldSense field session starting in $REPO_ROOT"
log "samples=$SAMPLES trigger=$TRIGGER require_fix=$REQUIRE_GPS_FIX simulate=$SIMULATE loop=$LOOP"

if ! "$PYTHON" -c "import fieldsense" >/dev/null 2>&1; then
  log "FATAL: cannot import fieldsense from $REPO_ROOT"
  exit 1
fi

if [ "$LOOP" = "1" ]; then
  log "loop mode: a new session starts as soon as the previous one finishes"
  while true; do
    run_session
    sleep 5
  done
else
  run_session
  exit $?
fi
