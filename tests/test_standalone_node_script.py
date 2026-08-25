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


def _unit_dependency_lines(body):
    """Return only the ordering/requirement directives of a unit file.

    Checked directive by directive rather than by substring: the unit explains in
    a comment WHY it must outlast arduino-app-cli.service, which itself wants
    network-online.target. A raw `"network-online.target" not in body` would read
    that explanation as a dependency and fail on prose.
    """
    keys = ("After=", "Wants=", "Requires=", "BindsTo=", "Requisite=")
    return [ln.strip() for ln in body.splitlines()
            if ln.strip().startswith(keys)]


def test_standalone_unit_requires_no_network():
    """An offline instrument must boot with the radios off."""
    deps = _unit_dependency_lines(_read(UNIT))
    assert deps, "unit declares no ordering at all"
    for line in deps:
        assert "network-online.target" not in line, \
            "unit takes a network dependency: {}".format(line)
        assert "network.target" not in line, \
            "unit takes a network dependency: {}".format(line)


def test_standalone_unit_is_ordered_after_app_lab():
    """App Lab flashes the MCU on start; racing it contends for the SWD lines.

    Without this ordering the node can start first, find no gateway, and restart
    the app while App Lab is still mid-flash. Two openocd sessions on the same
    SWD lines fail with `Error requesting gpio line swdio`, which needs
    `sudo killall -9 openocd` — impossible on an unattended node.
    """
    body = _read(UNIT)
    after = [l for l in _unit_dependency_lines(body) if l.startswith("After=")]
    assert after, "no After= directive"
    assert any("arduino-app-cli.service" in l for l in after), after
    assert any("docker.service" in l for l in after), after
    assert any("local-fs.target" in l for l in after), after


def test_standalone_unit_names_no_model_file():
    """The unit must not pin a model path; discovery resolves the real one.

    FIELDSENSE_MODEL_PATH used to name models/fieldsense-slm.gguf, which has
    never existed on the board. Because the environment outranks discovery, that
    single line forced the template backend while Qwen sat in models/.
    """
    body = _read(UNIT)
    env = [ln.strip() for ln in body.splitlines()
           if ln.strip().startswith("Environment=")]
    assert env, "unit sets no Environment= at all"
    for line in env:
        assert "FIELDSENSE_MODEL_PATH" not in line, \
            "unit pins a model path: {}".format(line)
        assert "fieldsense-slm.gguf" not in line, \
            "unit pins a nonexistent model file: {}".format(line)
    assert "Environment=FIELDSENSE_AI_BACKEND=AUTO" in body


def test_node_waits_for_the_gateway_before_reflashing():
    """A slow App Lab start must not be answered with a second flash."""
    body = _read(SCRIPT)
    assert "wait_for_gateway" in body
    assert "GATEWAY_WAIT_SECONDS" in body
    # The wait must be attempted BEFORE the restart, or it buys nothing.
    assert body.index("if wait_for_gateway") < body.index("app restart")


def test_installer_offers_the_standalone_unit():
    body = _read(INSTALLER)
    assert "--standalone" in body
    assert "fieldsense-standalone.service" in body


@needs_bash
def test_installer_is_valid_bash():
    result = subprocess.run(["bash", "-n", INSTALLER], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_installer_flushes_the_unit_to_disk():
    """A zero-length unit reads as MASKED, and the node vanishes silently.

    An install followed seconds later by a power cut left the unit at zero bytes:
    ext4 ordered mode journals metadata, so the enable symlink survived while the
    file contents did not. A field node is installed and then power-cycled almost
    by definition, so this window is the normal case.
    """
    body = _read(INSTALLER)
    assert "run sync" in body
    assert body.index("systemctl enable") < body.index("run sync")
