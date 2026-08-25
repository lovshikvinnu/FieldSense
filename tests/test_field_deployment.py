"""The field session launcher and its systemd unit, read as text.

Same reasoning as tests/test_standalone_node_script.py: the far side of these
files is an unattended boot on a board in a field. A wrong Environment= line or
a missing dependency is invisible until a power cycle that nobody is watching,
so the properties that matter are pinned here.

Nothing is installed, started, or executed against systemd.
"""

import os
import re
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "run_field_session.sh")
UNIT = os.path.join(REPO, "deploy", "fieldsense-field.service")
INSTALLER = os.path.join(REPO, "scripts", "install_boot_service.sh")


def read(path):
    if not os.path.exists(path):
        pytest.fail("missing deployment file: {}".format(path))
    return open(path, encoding="utf-8").read()


# ------------------------------------------------------------- script


def test_the_launcher_exists_and_is_executable():
    """A unit whose ExecStart is not executable fails with a bare 203/EXEC."""
    assert os.path.isfile(SCRIPT)
    assert os.access(SCRIPT, os.X_OK)


def test_the_launcher_is_valid_bash():
    subprocess.run(["bash", "-n", SCRIPT], check=True)


def test_the_launcher_help_changes_nothing():
    result = subprocess.run(["bash", SCRIPT, "--help"],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert "field session" in result.stdout.lower()


def test_the_launcher_drives_the_field_node():
    assert "-m fieldsense.field_node" in read(SCRIPT)


def test_the_launcher_pushes_over_the_router_proxy_not_a_framebuffer():
    """The QRB2210 routes no SPI to the headers, so no /dev/fbN can reach it."""
    source = read(SCRIPT)
    assert "127.0.0.1:7500" in source
    assert "--panel" in source
    assert "/dev/fb" not in source


def test_the_launcher_autodiscovers_the_gateway_container():
    """The container address changes on every App Lab rebuild."""
    source = read(SCRIPT)
    assert "docker exec" in source and "hostname -i" in source


def test_the_launcher_waits_for_the_gateway_before_reflashing():
    """A restart mid-flash puts a second openocd on the same SWD lines."""
    source = read(SCRIPT)
    wait_at = source.index("wait_for_gateway")
    restart_at = source.index("arduino-app-cli app restart")
    assert wait_at < restart_at, "the restart must come after the wait"


def test_the_launcher_does_not_carry_a_resume_into_the_next_session():
    """Otherwise --loop would append a new survey to the previous session."""
    source = read(SCRIPT)
    assert re.search(r'^\s*RESUME=""\s*$', source, re.M), \
        "RESUME must be cleared after each session"


def test_the_launcher_defaults_to_the_operator_trigger():
    """'auto' advances samples on a timer, which is not an operator."""
    assert 'TRIGGER="${TRIGGER:-any}"' in read(SCRIPT)


# --------------------------------------------------------------- unit


def test_the_unit_runs_the_field_launcher():
    assert "run_field_session.sh" in read(UNIT)


def test_the_unit_requires_no_network_of_any_kind():
    """The device must come up with the radios off."""
    source = read(UNIT)
    for token in ("network-online.target", "network.target"):
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue          # the comments explain why, and may name it
            assert token not in stripped, \
                "{} appears in a directive: {!r}".format(token, stripped)


def test_the_unit_is_ordered_after_app_lab_and_the_router():
    source = read(UNIT)
    after = [l for l in source.splitlines() if l.startswith("After=")]
    assert after, "no After= line"
    assert "arduino-app-cli.service" in after[0]
    assert "arduino-router.service" in after[0]
    assert "docker.service" in after[0]


def test_the_unit_names_no_model_file():
    """FIELDSENSE_MODEL_PATH outranks discovery and once forced the fallback."""
    for line in read(UNIT).splitlines():
        if line.strip().startswith("Environment=FIELDSENSE_MODEL_PATH"):
            pytest.fail("the unit pins a model path: {!r}".format(line.strip()))


def test_the_unit_selects_the_operator_trigger():
    """'enter' needs a TTY this unit has none of; 'auto' is not an operator."""
    source = read(UNIT)
    assert "Environment=TRIGGER=any" in source
    for bad in ("Environment=TRIGGER=auto", "Environment=TRIGGER=enter"):
        assert bad not in source


def test_the_unit_can_read_the_boards_own_buttons():
    """The evdev node is root:input. Without the group the node waits forever."""
    groups = [l for l in read(UNIT).splitlines()
              if l.startswith("SupplementaryGroups=")]
    assert groups and "input" in groups[0], \
        "the unit cannot read /dev/input without the 'input' group"


def test_the_unit_does_not_pin_a_resume_session():
    """A unit that resumed on every boot would merge separate field surveys."""
    for line in read(UNIT).splitlines():
        assert not line.strip().startswith("Environment=RESUME="), \
            "the unit pins RESUME: {!r}".format(line.strip())


def test_the_unit_can_reach_the_probe_and_the_app_lab_container():
    source = read(UNIT)
    groups = [l for l in source.splitlines() if l.startswith("SupplementaryGroups=")]
    assert groups, "no SupplementaryGroups= line"
    assert "dialout" in groups[0] and "docker" in groups[0]


def test_the_unit_restarts_rather_than_leaving_a_stale_panel():
    assert "Restart=always" in read(UNIT)


def test_the_unit_does_not_protect_away_its_own_working_directory():
    """ProtectHome=yes would hide /home/arduino, which is WorkingDirectory."""
    source = read(UNIT)
    for line in source.splitlines():
        assert not line.strip().startswith("ProtectHome=yes"), \
            "ProtectHome would hide this unit's own WorkingDirectory"


# ---------------------------------------------------------- installer


def test_the_installer_offers_the_field_unit():
    source = read(INSTALLER)
    assert "--field" in source
    assert "fieldsense-field.service" in source


def test_the_installer_makes_the_field_launcher_executable():
    assert "run_field_session.sh" in read(INSTALLER)


def test_the_installer_is_still_valid_bash():
    subprocess.run(["bash", "-n", INSTALLER], check=True)
