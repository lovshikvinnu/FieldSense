#!/usr/bin/env bash
#
# FieldSense AI — install the standalone boot service on the Arduino UNO Q.
#
#   sudo ./scripts/install_boot_service.sh                    # one-shot boot unit
#   sudo ./scripts/install_boot_service.sh --refresh          # continuous loop unit
#   sudo ./scripts/install_boot_service.sh --standalone       # autonomous field node
#                                                             # (probe + GPS + panel
#                                                             #  over the router bridge)
#   sudo ./scripts/install_boot_service.sh --field            # operator-driven field
#                                                             # session: one sample per
#                                                             # press, stored as it goes
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
    # The standalone node runs from the board user's own checkout, because it
    # needs docker access to reach the App Lab container. Copying it to
    # /opt under a system account would break that.
    --standalone)
        UNIT="fieldsense-standalone.service"
        SERVICE_USER="${SUDO_USER:-arduino}"
        PREFIX="$REPO_ROOT"
        shift ;;
    # The field session unit runs from the board user's checkout for the same
    # reason as --standalone: it needs docker access to find the App Lab
    # container, which a system account under /opt does not have.
    --field)
        UNIT="fieldsense-field.service"
        SERVICE_USER="${SUDO_USER:-arduino}"
        PREFIX="$REPO_ROOT"
        shift ;;
    --prefix)   PREFIX="$2"; shift 2 ;;
    --user)     SERVICE_USER="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  sed -n '2,17p' "$0"; exit 0 ;;
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
#
# --standalone deliberately sets PREFIX to the repository itself, because the
# node needs docker access to reach the App Lab container and a /opt copy under
# a system account would not have it. Copying a tree onto itself is then not
# merely redundant, it is unsafe: this image has no rsync, and the tar fallback
# streams `tar -cf - .` into `tar -xf -` over the SAME directory, extracting
# files while they are still being read. That branch also does not exclude
# models/, so it would pipe ~1.2 GB of GGUF weights onto themselves and could
# leave the very weights the node is about to load truncated.
#
# Nothing needs copying when source and destination are the same tree, so skip.
echo "==> installing the application to $PREFIX"
if [ "$(cd "$REPO_ROOT" 2>/dev/null && pwd -P)" = "$(cd "$PREFIX" 2>/dev/null && pwd -P)" ]; then
  echo "    source and destination are the same tree; nothing to copy"
else
  run mkdir -p "$PREFIX"
  if command -v rsync >/dev/null 2>&1; then
    run rsync -a --delete \
      --exclude '.git' --exclude '__pycache__' --exclude '.pytest_cache' \
      --exclude 'models' \
      "$REPO_ROOT"/ "$PREFIX"/
  else
    # tar keeps this working on an image without rsync. models/ is excluded here
    # too, matching the rsync branch: weights are large and are deployed
    # separately, never streamed through the installer.
    if [ "$DRY_RUN" = "1" ]; then
      echo "  would run: tar -C $REPO_ROOT -cf - . | tar -C $PREFIX -xf -"
    else
      tar -C "$REPO_ROOT" --exclude='.git' --exclude='__pycache__' \
          --exclude='.pytest_cache' --exclude='models' -cf - . | tar -C "$PREFIX" -xf -
    fi
  fi
fi
run mkdir -p "$PREFIX/artifacts" "$PREFIX/models"
run chown -R "$SERVICE_USER":"$SERVICE_USER" "$PREFIX"
run chmod +x "$PREFIX/scripts/boot_fieldsense.sh" "$PREFIX/scripts/launch_display.sh"
# The two node launchers, whichever unit was selected. A unit whose ExecStart is
# not executable fails at start with a bare 203/EXEC and no explanation.
for launcher in run_standalone_node.sh run_field_session.sh; do
  [ -f "$PREFIX/scripts/$launcher" ] && run chmod +x "$PREFIX/scripts/$launcher"
done

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

# 6. Force the unit to disk before returning.
#
# NOT DEFENSIVE PROGRAMMING - this exact failure has happened. An install
# followed within seconds by a power cut left
# /etc/systemd/system/fieldsense-standalone.service at ZERO BYTES: ext4 in
# ordered mode journals the metadata, so the directory entry and the enable
# symlink both survived, while the file's data blocks were never written.
# systemd reports a zero-length unit as MASKED, so the node silently did not
# exist at the next boot, with `systemctl is-enabled` answering "masked" and no
# log line anywhere to explain it.
#
# A field node is installed and then immediately power-cycled almost by
# definition, so the window is the normal case here, not an edge case.
run sync

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
