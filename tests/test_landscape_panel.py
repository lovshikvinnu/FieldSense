"""Hold the panel firmware to the landscape layout it claims.

The far side of this layout is firmware. A coordinate that runs off the bottom
of the screen, or an instruction string too long for the width it is drawn in,
is invisible until someone flashes a board and looks at it — and on the UNO Q a
flash-and-look cycle is about ninety seconds. These tests read the .ino files as
text so a clipped layout fails here instead.

Nothing is compiled or flashed. The sketches are parsed as source.
"""

import os
import re

import pytest

from fieldsense.field.panel import ACTION_LINES

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOYED = os.path.join(REPO_ROOT, "hardware_test", "fieldsense_unoq", "fieldsense_unoq.ino")
DISPLAY_ONLY = os.path.join(REPO_ROOT, "hardware_test", "TFT_UNOQ", "dashboard", "dashboard.ino")
SKETCHES = (DEPLOYED, DISPLAY_ONLY)

# Adafruit_GFX's built-in font, which both sketches use.
CHAR_W = 6
CHAR_H = 8

# Must match the sketches' MARGIN and ACTION_H.
MARGIN = 6
ACTION_BOX_W = 320 - 2 * MARGIN
DRAW_CENTERED_PADDING = 8      # drawCentered() reserves this inside the box


def _read(path):
    if not os.path.exists(path):
        pytest.skip("sketch not present: {}".format(path))
    return open(path, encoding="utf-8", errors="replace").read()


#: Constants the layout expressions are allowed to reference. Resolved first so
#: a definition like `SOIL_COL_A = MARGIN + 8` can be evaluated here exactly as
#: the compiler would, rather than forcing every constant in the sketch to be a
#: bare literal purely so a test can read it.
_BASE_CONSTS = ("PANEL_W", "PANEL_H", "MARGIN")


def _const(source, name, _seen=None):
    """Read one layout constant, resolving simple arithmetic on other constants."""
    match = re.search(
        r"\b{}\s*=\s*([-+*/ 0-9A-Z_a-z]+?)\s*[;,]".format(re.escape(name)), source)
    assert match, "layout constant {} not found".format(name)
    expression = match.group(1).strip()

    seen = set(_seen or ())
    assert name not in seen, "circular layout constant: {}".format(name)
    seen.add(name)

    scope = {}
    for base in _BASE_CONSTS:
        if base != name and re.search(r"\b{}\b".format(base), expression):
            scope[base] = _const(source, base, seen)
    try:
        return int(eval(expression, {"__builtins__": {}}, scope))  # noqa: S307
    except Exception as exc:  # pragma: no cover - a malformed sketch constant
        raise AssertionError(
            "could not evaluate {} = {!r}: {}".format(name, expression, exc))


def _fit_size(text, width, max_size):
    """Mirror of the sketch's fitTextSize(): largest size that fits, floor 1."""
    if not text:
        return max_size
    for size in range(max_size, 1, -1):
        if len(text) * CHAR_W * size <= width:
            return size
    return 1


# ------------------------------------------------------- orientation


@pytest.mark.parametrize("path", SKETCHES)
def test_the_panel_boots_directly_into_landscape(path):
    """Not rotated later, not left to the host: landscape from setup()."""
    source = _read(path)
    assert _const(source, "PANEL_ROTATION") == 1
    assert re.search(r"tft\.setRotation\(\s*PANEL_ROTATION\s*\)", source), \
        "setRotation must use PANEL_ROTATION so the constant cannot drift from the call"


@pytest.mark.parametrize("path", SKETCHES)
def test_the_drawing_surface_is_320_by_240(path):
    source = _read(path)
    assert _const(source, "PANEL_W") == 320
    assert _const(source, "PANEL_H") == 240


@pytest.mark.parametrize("path", SKETCHES)
def test_init_is_given_the_native_geometry_not_the_rotated_one(path):
    """init() takes the glass's real 240x320; setRotation does the rest.

    Passing the rotated size here is the classic version of this bug: the
    driver sets its address window from these numbers, so a 320x240 init
    produces a display that scrolls or wraps rather than one that is landscape.
    """
    source = _read(path)
    assert re.search(r"tft\.init\(\s*240\s*,\s*320\s*\)", source), \
        "tft.init() must be given the native 240x320 panel geometry"


@pytest.mark.parametrize("path", SKETCHES)
def test_no_portrait_geometry_survives_in_the_layout(path):
    """A leftover 240-wide assumption would hug everything to the left third."""
    source = _read(path)
    for name in ("HEADER_Y", "GPS_Y", "ACTION_Y", "SOIL_Y", "BAR_Y"):
        assert _const(source, name) < 240, \
            "{} is below a 240-tall landscape screen".format(name)


# ----------------------------------------------------------- fit


@pytest.mark.parametrize("path", SKETCHES)
def test_every_band_fits_inside_the_screen(path):
    """Bands must tile the height without running off the bottom edge."""
    source = _read(path)
    height = _const(source, "PANEL_H")
    bands = [
        (_const(source, "HEADER_Y"), _const(source, "HEADER_H")),
        (_const(source, "GPS_Y"), _const(source, "GPS_H")),
        (_const(source, "ACTION_Y"), _const(source, "ACTION_H")),
        (_const(source, "SOIL_Y"), _const(source, "SOIL_H")),
        (_const(source, "BAR_Y"), _const(source, "BAR_H")),
    ]
    for top, band_height in bands:
        assert top + band_height <= height, \
            "band at y={} height={} overruns the {}px screen".format(top, band_height, height)


@pytest.mark.parametrize("path", SKETCHES)
def test_the_bands_do_not_overlap(path):
    """Overlapping bands are how two values end up drawn on top of each other."""
    source = _read(path)
    bands = sorted([
        (_const(source, "HEADER_Y"), _const(source, "HEADER_H")),
        (_const(source, "GPS_Y"), _const(source, "GPS_H")),
        (_const(source, "ACTION_Y"), _const(source, "ACTION_H")),
        (_const(source, "SOIL_Y"), _const(source, "SOIL_H")),
        (_const(source, "BAR_Y"), _const(source, "BAR_H")),
    ])
    for (top, height), (next_top, _) in zip(bands, bands[1:]):
        assert top + height <= next_top, \
            "band at y={} (h={}) overlaps the band at y={}".format(top, height, next_top)


@pytest.mark.parametrize("path", SKETCHES)
def test_the_soil_columns_use_the_full_width(path):
    """Two columns are the whole reason for landscape; one column wastes it."""
    source = _read(path)
    col_a = _const(source, "SOIL_COL_A")
    assert col_a < 160, "the first soil column should start in the left half"
    assert re.search(r"SOIL_COL_B\s*=\s*PANEL_W\s*/\s*2", source), \
        "the second soil column should be derived from the panel width"


@pytest.mark.parametrize("path", SKETCHES)
def test_the_soil_rows_fit_inside_their_card(path):
    source = _read(path)
    row_h = _const(source, "SOIL_ROW_H")
    # Four label/value rows are drawn, the first at +6 from the card top.
    assert 6 + row_h * 3 + CHAR_H <= _const(source, "SOIL_H"), \
        "four soil rows do not fit inside SOIL_H"


# ------------------------------------------------ operator instructions


def test_every_operator_instruction_fits_the_landscape_width():
    """The host must not be able to send an instruction the panel would clip.

    drawCentered() truncates rather than overflowing, so a too-long string
    would not corrupt the layout - it would silently drop the end of the
    sentence, which on an instruction line is worse.
    """
    width = ACTION_BOX_W - DRAW_CENTERED_PADDING
    for state, template in ACTION_LINES.items():
        text = template.format(i=8, m=8)
        size = _fit_size(text, width, 3)
        assert len(text) * CHAR_W * size <= width, \
            "{}: {!r} clips even at text size 1".format(state.value, text)


def test_the_instructions_stay_large_enough_to_read_at_arms_length():
    """Every instruction should reach at least size 2, i.e. 16px tall glyphs."""
    width = ACTION_BOX_W - DRAW_CENTERED_PADDING
    for state, template in ACTION_LINES.items():
        text = template.format(i=8, m=8)
        assert _fit_size(text, width, 3) >= 2, \
            "{}: {!r} is too long to render above text size 1".format(state.value, text)


def test_the_headline_saved_message_gets_the_largest_size():
    """SAMPLE N SAVED is the confirmation an operator looks for from a distance."""
    text = ACTION_LINES[list(ACTION_LINES)[3]].format(i=1, m=5)
    assert _fit_size(text, ACTION_BOX_W - DRAW_CENTERED_PADDING, 3) == 3


# ------------------------------------------------------- both sketches


def test_both_sketches_share_the_same_layout_constants():
    """The bench panel and the field panel must not drift into two layouts."""
    deployed, display = _read(DEPLOYED), _read(DISPLAY_ONLY)
    for name in ("PANEL_W", "PANEL_H", "PANEL_ROTATION", "HEADER_Y", "HEADER_H",
                 "GPS_Y", "GPS_H", "ACTION_Y", "ACTION_H", "SOIL_Y", "SOIL_H",
                 "BAR_Y", "BAR_H", "MARGIN", "SOIL_ROW_H"):
        assert _const(deployed, name) == _const(display, name), \
            "{} differs between the two sketches".format(name)


def test_the_repo_layout_constants_match_the_ones_these_tests_assume():
    """Guard the constants this file hard-codes against a silent sketch edit."""
    source = _read(DEPLOYED)
    assert _const(source, "MARGIN") == MARGIN
    assert _const(source, "CHAR_W") == CHAR_W
    assert _const(source, "CHAR_H") == CHAR_H
    assert _const(source, "ACTION_H") >= CHAR_H * 3, \
        "the action band must be tall enough for size-3 text"
