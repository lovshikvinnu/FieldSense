#!/usr/bin/env bash
#
# FieldSense AI — install the standalone boot service on the Arduino UNO Q.
#
#   sudo ./scripts/install_boot_service.sh                    # one-shot boot unit
#   sudo ./scripts/install_boot_service.sh --refresh          # continuous loop unit
#   sudo ./scripts/install_boot_service.sh --prefix /srv/fs   # different install root
#   sudo ./scripts/install_boot_service.sh --dry-run          # print, change nothing
#
# Copies the repository to PREFIX, creates the service account, adds it to the
# groups that own the framebuffer and the serial port, installs the unit, and
# enables it. Idempotent: safe to re-run after a code change.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PREFIX="/opt/fieldsense"
SERVICE_USER="fieldsense"
UNIT="fieldsense.service"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --refresh)  UNIT="fieldsense-refresh.service"; shift ;;
    --prefix)   PREFIX="$2"; shift 2 ;;
    --user)     SERVICE_USER="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  sed -n '2,14p' "$0"; exit 0 ;;
    *)          echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

run() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '  would run: %s\n' "$*"
  else
    "$@"
  fi
}

if [ "$DRY_RUN" = "0" ] && [ "$(id -u)" != "0" ]; then
  echo "This installer writes to $PREFIX and /etc/systemd/system; run it with sudo." >&2
  echo "To preview without changing anything:  ./scripts/install_boot_service.sh --dry-run" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found. This installer targets the UNO Q's systemd-based" >&2
  echo "Debian image. On another init system, run scripts/boot_fieldsense.sh" >&2
  echo "from your own startup mechanism instead." >&2
  # A dry run is still useful off-target: it shows exactly what would happen.
  [ "$DRY_RUN" = "1" ] || exit 1
fi

echo "==> FieldSense boot service installer"
echo "    source : $REPO_ROOT"
echo "    prefix : $PREFIX"
echo "    unit   : $UNIT"
echo "    user   : $SERVICE_USER"
[ "$DRY_RUN" = "1" ] && echo "    MODE   : DRY RUN, nothing will change"

# 1. Service account. A system account with no login shell; it only needs to
#    read the repo, write artifacts, open a tty, and write a framebuffer.
if id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "==> user $SERVICE_USER already exists"
else
  echo "==> creating system user $SERVICE_USER"
  run useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# 2. Group membership. Without 'video' the panel write fails with EACCES; without
#    'dialout' the RS485 probe cannot be opened. Both are silent-until-runtime.
for group in video dialout; do
  if getent group "$group" >/dev/null 2>&1; then
    echo "==> adding $SERVICE_USER to $group"
    run usermod -aG "$group" "$SERVICE_USER"
  else
    echo "    [!] group $group does not exist on this image; skipping"
  fi
done

# 3. Payload.
echo "==> installing the application to $PREFIX"
run mkdir -p "$PREFIX"
if command -v rsync >/dev/null 2>&1; then
  run rsync -a --delete \
    --exclude '.git' --exclude '__pycache__' --exclude '.pytest_cache' \
    --exclude 'models' \
    "$REPO_ROOT"/ "$PREFIX"/
else
  # tar keeps this working on an image without rsync.
  if [ "$DRY_RUN" = "1" ]; then
    echo "  would run: tar -C $REPO_ROOT -cf - . | tar -C $PREFIX -xf -"
  else
    tar -C "$REPO_ROOT" --exclude='.git' --exclude='__pycache__' \
        --exclude='.pytest_cache' -cf - . | tar -C "$PREFIX" -xf -
  fi
fi
run mkdir -p "$PREFIX/artifacts" "$PREFIX/models"
run chown -R "$SERVICE_USER":"$SERVICE_USER" "$PREFIX"
run chmod +x "$PREFIX/scripts/boot_fieldsense.sh" "$PREFIX/scripts/launch_display.sh"

# 4. Unit file, with the prefix and user substituted in.
echo "==> installing /etc/systemd/system/$UNIT"
if [ "$DRY_RUN" = "1" ]; then
  echo "  would install $REPO_ROOT/deploy/$UNIT with /opt/fieldsense -> $PREFIX"
else
  sed -e "s#/opt/fieldsense#$PREFIX#g" \
      -e "s#^User=fieldsense\$#User=$SERVICE_USER#" \
      "$REPO_ROOT/deploy/$UNIT" > "/etc/systemd/system/$UNIT"
fi

# 5. Enable.
echo "==> enabling $UNIT"
run systemctl daemon-reload
run systemctl enable "$UNIT"

echo
echo "==> Done. Start it now and watch the log:"
echo "      sudo systemctl start $UNIT"
echo "      journalctl -u ${UNIT%.service} -f"
echo
echo "    Switch to live hardware by editing the Environment= lines in"
echo "      /etc/systemd/system/$UNIT"
echo "    then:  sudo systemctl daemon-reload && sudo systemctl restart $UNIT"
echo
echo "    Verify the display path first with:"
echo "      sudo -u $SERVICE_USER $PREFIX/scripts/launch_display.sh probe"
