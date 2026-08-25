"""Tests for the run_standalone_node.sh field-node launcher and its systemd unit.

These guard the deployment path itself, which is otherwise only exercised on
physical hardware. The regression they exist to prevent: a boot service that
pushes the panel through a Linux framebuffer. On the UNO Q the QRB2210 routes
no SPI to the external headers, so no /dev/fbN can exist for this panel and the
screen silently stays dark.
"""

import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "run_standalone_node.sh")
UNIT = os.path.join(REPO, "deploy", "fieldsense-standalone.service")
INSTALLER = os.path.join(REPO, "scripts", "install_boot_service.sh")

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_standalone_script_exists_and_is_executable():
    assert os.path.isfile(SCRIPT)
    assert os.access(SCRIPT, os.X_OK), "run_standalone_node.sh must be executable on the board"


@needs_bash
def test_standalone_script_is_valid_bash():
    result = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@needs_bash
def test_standalone_script_help_runs_without_side_effects():
    result = subprocess.run([SCRIPT, "--help"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert "standalone field node" in result.stdout.lower()


def test_standalone_script_pushes_over_the_bridge_not_a_framebuffer():
    """The whole reason this unit exists."""
    body = _read(SCRIPT)
    assert "--display bridge" in body
    assert "--mcu-port" in body

    # A framebuffer may be *mentioned* in comments explaining why it cannot
    # work here; what must not appear is any code that actually targets one.
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    assert "--fb" not in code
    assert "FB_DEVICE" not in code
    assert "--display auto" not in code and "--display force" not in code


def test_standalone_script_drives_the_v1_runner():
    assert "fieldsense.v1_runner" in _read(SCRIPT)


def test_standalone_script_gates_on_a_real_gps_fix_by_default():
    """A cycle with no lock records every point at 0,0 and must be skipped."""
    body = _read(SCRIPT)
    assert 'REQUIRE_GPS_FIX="${REQUIRE_GPS_FIX:-1}"' in body
    assert "FIX_OK" in body
    assert "skipping this cycle" in body


def test_standalone_script_autodiscovers_the_gateway_container():
    """The App Lab container address changes on every rebuild."""
    body = _read(SCRIPT)
    assert "hostname -i" in body
    assert "GATEWAY_HOST:-auto" in body


def test_standalone_unit_exists_and_targets_the_bridge_path():
    body = _read(UNIT)
    assert "run_standalone_node.sh --loop" in body
    assert "WantedBy=multi-user.target" in body
    assert "Restart=always" in body


def test_standalone_unit_depends_on_docker_for_app_lab():
    body = _read(UNIT)
    assert "docker.service" in body
    assert "SupplementaryGroups=dialout docker" in body


def test_standalone_unit_requires_no_network():
    """An offline instrument must boot with the radios off."""
    body = _read(UNIT)
    assert "network-online.target" not in body
    assert "After=docker.service local-fs.target" in body


def test_installer_offers_the_standalone_unit():
    body = _read(INSTALLER)
    assert "--standalone" in body
    assert "fieldsense-standalone.service" in body


@needs_bash
def test_installer_is_valid_bash():
    result = subprocess.run(["bash", "-n", INSTALLER], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
