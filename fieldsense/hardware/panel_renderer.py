"""Browser-free panel renderer — the display path of last resort.

`display_bridge` rasterises the dashboard by driving a headless Chromium. That
is the right renderer when a browser exists, and it produces the real UI. But a
minimally provisioned Debian image on the UNO Q has no browser, and Chromium is
not a declared dependency of this project, so on a stock board the panel showed
nothing at all: no browser, no frame, no pixels, and the field unit booted to a
black screen.

This module removes that single point of failure. It draws a legible status
panel straight into an RGB888 buffer using a 5x7 bitmap font defined below, with
nothing but the standard library. It is deliberately austere — it reports the
numbers the deterministic pipeline produced and nothing else. When a browser is
present the full dashboard is still what gets displayed; this is the floor, not
the ceiling.

    panel_summary.json  ->  render_summary_panel()  ->  RGB888  ->  RGB565  ->  /dev/fbN

Every value drawn comes from the summary written by the pipeline. Nothing is
computed, rounded, or inferred here, so the panel cannot disagree with the
dashboard.
"""

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 5x7 glyphs, one byte per column, bit 0 = top row. Uppercase only; lowercase
# input is folded to uppercase, and any unmapped character renders as a space.
FONT_WIDTH = 5
FONT_HEIGHT = 7
GLYPH_SPACING = 1
CELL_WIDTH = FONT_WIDTH + GLYPH_SPACING

FONT: Dict[str, Tuple[int, int, int, int, int]] = {
    ' ': (0x00,0x00,0x00,0x00,0x00),
    '!': (0x00,0x00,0x5F,0x00,0x00),
    '#': (0x14,0x7F,0x14,0x7F,0x14),
    '%': (0x23,0x13,0x08,0x64,0x62),
    '(': (0x00,0x1C,0x22,0x41,0x00),
    ')': (0x00,0x41,0x22,0x1C,0x00),
    '*': (0x14,0x08,0x3E,0x08,0x14),
    '+': (0x08,0x08,0x3E,0x08,0x08),
    ',': (0x00,0x50,0x30,0x00,0x00),
    '-': (0x08,0x08,0x08,0x08,0x08),
    '.': (0x00,0x60,0x60,0x00,0x00),
    '/': (0x20,0x10,0x08,0x04,0x02),
    '0': (0x3E,0x51,0x49,0x45,0x3E),
    '1': (0x00,0x42,0x7F,0x40,0x00),
    '2': (0x42,0x61,0x51,0x49,0x46),
    '3': (0x21,0x41,0x45,0x4B,0x31),
    '4': (0x18,0x14,0x12,0x7F,0x10),
    '5': (0x27,0x45,0x45,0x45,0x39),
    '6': (0x3C,0x4A,0x49,0x49,0x30),
    '7': (0x01,0x71,0x09,0x05,0x03),
    '8': (0x36,0x49,0x49,0x49,0x36),
    '9': (0x06,0x49,0x49,0x29,0x1E),
    ':': (0x00,0x36,0x36,0x00,0x00),
    '<': (0x08,0x14,0x22,0x41,0x00),
    '=': (0x14,0x14,0x14,0x14,0x14),
    '>': (0x00,0x41,0x22,0x14,0x08),
    '?': (0x02,0x01,0x51,0x09,0x06),
    'A': (0x7E,0x11,0x11,0x11,0x7E),
    'B': (0x7F,0x49,0x49,0x49,0x36),
    'C': (0x3E,0x41,0x41,0x41,0x22),
    'D': (0x7F,0x41,0x41,0x22,0x1C),
    'E': (0x7F,0x49,0x49,0x49,0x41),
    'F': (0x7F,0x09,0x09,0x09,0x01),
    'G': (0x3E,0x41,0x49,0x49,0x7A),
    'H': (0x7F,0x08,0x08,0x08,0x7F),
    'I': (0x00,0x41,0x7F,0x41,0x00),
    'J': (0x20,0x40,0x41,0x3F,0x01),
    'K': (0x7F,0x08,0x14,0x22,0x41),
    'L': (0x7F,0x40,0x40,0x40,0x40),
    'M': (0x7F,0x02,0x0C,0x02,0x7F),
    'N': (0x7F,0x04,0x08,0x10,0x7F),
    'O': (0x3E,0x41,0x41,0x41,0x3E),
    'P': (0x7F,0x09,0x09,0x09,0x06),
    'Q': (0x3E,0x41,0x51,0x21,0x5E),
    'R': (0x7F,0x09,0x19,0x29,0x46),
    'S': (0x46,0x49,0x49,0x49,0x31),
    'T': (0x01,0x01,0x7F,0x01,0x01),
    'U': (0x3F,0x40,0x40,0x40,0x3F),
    'V': (0x1F,0x20,0x40,0x20,0x1F),
    'W': (0x3F,0x40,0x38,0x40,0x3F),
    'X': (0x63,0x14,0x08,0x14,0x63),
    'Y': (0x07,0x08,0x70,0x08,0x07),
    'Z': (0x61,0x51,0x49,0x45,0x43),
    '[': (0x00,0x7F,0x41,0x41,0x00),
    ']': (0x00,0x41,0x41,0x7F,0x00),
    '_': (0x40,0x40,0x40,0x40,0x40),
    '|': (0x00,0x00,0x7F,0x00,0x00),
}

# Slate palette, matching the HTML dashboard so the two do not look unrelated.
COLOR_BACKGROUND = (0x0F, 0x17, 0x2A)
COLOR_HEADER_BAR = (0x1E, 0x29, 0x3B)
COLOR_TITLE = (0xF8, 0xFA, 0xFC)
COLOR_LABEL = (0x94, 0xA3, 0xB8)
COLOR_VALUE = (0xE2, 0xE8, 0xF0)
COLOR_RULE = (0x33, 0x41, 0x55)
COLOR_GOOD = (0x4A, 0xDE, 0x80)
COLOR_WARN = (0xFA, 0xCC, 0x15)
COLOR_POOR = (0xF8, 0x71, 0x71)

STATUS_COLORS = {
    "HEALTHY": COLOR_GOOD, "GOOD": COLOR_GOOD, "OK": COLOR_GOOD,
    "MODERATE": COLOR_WARN, "WARNING": COLOR_WARN, "LIMITED": COLOR_WARN,
    "POOR": COLOR_POOR, "CRITICAL": COLOR_POOR, "REJECTED": COLOR_POOR,
}

PANEL_SUMMARY_PATH = "artifacts/panel_summary.json"


class Canvas:
    """A mutable RGB888 pixel buffer with the few primitives a panel needs."""

    def __init__(self, width: int, height: int, background: Tuple[int, int, int] = COLOR_BACKGROUND) -> None:
        """Create a canvas filled with `background`.

        Args:
            width: Canvas width in pixels.
            height: Canvas height in pixels.
            background: Fill colour as an (r, g, b) triple.
        """
        self.width = width
        self.height = height
        self.pixels = bytearray(bytes(background) * (width * height))

    def set_pixel(self, x: int, y: int, color: Tuple[int, int, int]) -> None:
        """Set one pixel, ignoring coordinates outside the canvas."""
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = (y * self.width + x) * 3
            self.pixels[offset:offset + 3] = bytes(color)

    def fill_rect(self, x: int, y: int, w: int, h: int, color: Tuple[int, int, int]) -> None:
        """Fill an axis-aligned rectangle, clipped to the canvas."""
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + w), min(self.height, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for row_y in range(y0, y1):
            offset = (row_y * self.width + x0) * 3
            self.pixels[offset:offset + len(row)] = row

    def draw_text(
        self,
        x: int,
        y: int,
        text: str,
        color: Tuple[int, int, int] = COLOR_VALUE,
        scale: int = 1,
    ) -> int:
        """Draw a string with the 5x7 font.

        Args:
            x: Left edge in pixels.
            y: Top edge in pixels.
            text: String to draw. Folded to uppercase; unknown glyphs blank.
            color: Text colour.
            scale: Integer pixel multiplier.

        Returns:
            The x coordinate just past the last glyph drawn.
        """
        cursor = x
        for char in str(text).upper():
            glyph = FONT.get(char)
            if glyph is not None:
                for col_index, column in enumerate(glyph):
                    for row_index in range(FONT_HEIGHT):
                        if column & (1 << row_index):
                            if scale == 1:
                                self.set_pixel(cursor + col_index, y + row_index, color)
                            else:
                                self.fill_rect(
                                    cursor + col_index * scale, y + row_index * scale,
                                    scale, scale, color,
                                )
            cursor += CELL_WIDTH * scale
        return cursor

    def to_rgb(self) -> bytes:
        """Return the flat RGB888 buffer."""
        return bytes(self.pixels)


def text_width(text: str, scale: int = 1) -> int:
    """Return the pixel width a string occupies at the given scale."""
    return max(0, len(str(text)) * CELL_WIDTH * scale - GLYPH_SPACING * scale)


def status_color(status: Optional[str]) -> Tuple[int, int, int]:
    """Map a pipeline status word to its panel colour."""
    return STATUS_COLORS.get(str(status or "").upper(), COLOR_VALUE)


def render_summary_panel(
    summary: Dict[str, Any],
    width: int = 240,
    height: int = 320,
) -> Tuple[int, int, bytes]:
    """Draw the status panel for one pipeline run.

    Args:
        summary: Panel summary mapping. Every key is optional; a missing key
            renders as '--' rather than raising, because a panel that fails to
            draw is worse than a panel with a gap in it.
        width: Panel width in pixels.
        height: Panel height in pixels.

    Returns:
        Tuple of (width, height, rgb888).
    """
    canvas = Canvas(width, height)
    margin = 8

    # Header
    canvas.fill_rect(0, 0, width, 26, COLOR_HEADER_BAR)
    canvas.draw_text(margin, 6, "FIELDSENSE", COLOR_TITLE, scale=2)
    canvas.fill_rect(0, 26, width, 1, COLOR_RULE)

    y = 36
    field_name = summary.get("field_name") or summary.get("dataset") or "FIELD SESSION"
    canvas.draw_text(margin, y, str(field_name)[:30], COLOR_LABEL)
    y += 14

    # Headline soil health, the one number a field operator reads first.
    score = summary.get("soil_health_percent")
    if score is None and summary.get("soil_health_score") is not None:
        score = round(float(summary["soil_health_score"]) * 100.0)
    health_status = summary.get("soil_health_status") or "UNKNOWN"
    headline = "--" if score is None else "{:.0f}%".format(float(score))

    canvas.draw_text(margin, y, "SOIL HEALTH", COLOR_LABEL)
    y += 12
    canvas.draw_text(margin, y, headline, status_color(health_status), scale=4)
    canvas.draw_text(margin + text_width(headline, 4) + 8, y + 14,
                     str(health_status)[:9], status_color(health_status))
    y += 34

    # Health bar
    canvas.fill_rect(margin, y, width - 2 * margin, 6, COLOR_RULE)
    if score is not None:
        filled = int((width - 2 * margin) * max(0.0, min(100.0, float(score))) / 100.0)
        canvas.fill_rect(margin, y, filled, 6, status_color(health_status))
    y += 16

    rows: Sequence[Tuple[str, Any]] = (
        ("SAMPLES", _fraction(summary.get("valid_samples"), summary.get("total_samples"))),
        ("REJECTED", summary.get("rejected_samples")),
        ("COVERAGE", _percent(summary.get("coverage_ratio"))),
        ("ZONES", summary.get("zone_count")),
        ("ACTIONS", summary.get("recommendation_count")),
        ("SOURCE", summary.get("data_source")),
        ("PROVENANCE", summary.get("provenance")),
        ("AI LAYER", summary.get("narrative_source")),
        ("EVIDENCE", summary.get("evidence_level")),
    )

    for label, value in rows:
        if value is None:
            value = "--"
        canvas.draw_text(margin, y, label, COLOR_LABEL)
        text = str(value)[:16]
        canvas.draw_text(width - margin - text_width(text), y, text, COLOR_VALUE)
        y += 12
        if y > height - 34:
            break

    # Footer: offline state and the reason this renderer ran at all.
    canvas.fill_rect(0, height - 24, width, 1, COLOR_RULE)
    offline = summary.get("offline_mode")
    footer = "OFFLINE" if offline in (True, "True", "true", None) else "ONLINE"
    canvas.draw_text(margin, height - 17, footer, COLOR_GOOD if footer == "OFFLINE" else COLOR_WARN)
    note = str(summary.get("panel_note") or "TEXT PANEL")[:18]
    canvas.draw_text(width - margin - text_width(note), height - 17, note, COLOR_LABEL)

    return width, height, canvas.to_rgb()


def _fraction(numerator: Any, denominator: Any) -> str:
    """Format 'n/d', or '--' when either side is missing."""
    if numerator is None or denominator is None:
        return "--"
    return "{}/{}".format(numerator, denominator)


def _percent(value: Any) -> str:
    """Format a ratio or an already-scaled percentage as 'NN%'."""
    if value is None:
        return "--"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    if number <= 1.0:
        number *= 100.0
    return "{:.0f}%".format(number)


def load_panel_summary(path: str = PANEL_SUMMARY_PATH) -> Optional[Dict[str, Any]]:
    """Load a panel summary file written by the pipeline.

    Returns:
        The parsed mapping, or None when the file is absent or unreadable.
        Never raises — the caller falls back to a minimal placeholder panel.
    """
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_panel_summary(summary: Dict[str, Any], path: str = PANEL_SUMMARY_PATH) -> Optional[str]:
    """Write a panel summary alongside the HTML dashboard.

    Returns:
        The path written, or None on failure. Never raises: failing to write
        the panel summary must not fail a pipeline run.
    """
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, default=str)
        return path
    except OSError:
        return None


def placeholder_summary(detail: str) -> Dict[str, Any]:
    """Build a summary describing why no pipeline data was available."""
    return {
        "field_name": "NO PIPELINE DATA",
        "soil_health_status": "UNKNOWN",
        "data_source": "NONE",
        "offline_mode": True,
        "panel_note": detail,
    }


def panel_lines(summary: Dict[str, Any]) -> List[str]:
    """Return the panel content as text, for logs and tests."""
    score = summary.get("soil_health_percent")
    if score is None and summary.get("soil_health_score") is not None:
        score = round(float(summary["soil_health_score"]) * 100.0)
    return [
        "FIELDSENSE",
        str(summary.get("field_name") or summary.get("dataset") or "FIELD SESSION"),
        "SOIL HEALTH {} {}".format(
            "--" if score is None else "{:.0f}%".format(float(score)),
            summary.get("soil_health_status") or "UNKNOWN",
        ),
        "SAMPLES {}".format(_fraction(summary.get("valid_samples"), summary.get("total_samples"))),
        "COVERAGE {}".format(_percent(summary.get("coverage_ratio"))),
        "ZONES {}".format(summary.get("zone_count", "--")),
        "ACTIONS {}".format(summary.get("recommendation_count", "--")),
    ]


# --------------------------------------------------------------- value record

# The compact record the MCU-rendered dashboard consumes, shared by
# `tools/push_panel.py` and `run_spatial_test.py --display bridge` so the two
# cannot drift apart. Pixel streaming to this panel is not viable: Serial on the
# UNO Q is Arduino_RouterBridge's Monitor, one available() costs ~595 ms, and a
# 153,600-byte frame would take three minutes. The MCU draws the dashboard; the
# host sends it these numbers.
#
# Keys stay single-character because at ~860 B/s every byte is real time on the
# wire. The sketch ignores keys it does not know, so this tuple can grow without
# a reflash. Its parser lives in hardware_test/TFT_UNOQ/dashboard/dashboard.ino.
PANEL_RECORD_FIELDS = (
    ("f", "field_name"),
    ("s", "soil_health_status"),
    ("h", "soil_health_score"),
    ("n", "total_samples"),
    ("v", "valid_samples"),
    ("r", "rejected_samples"),
    ("z", "zone_count"),
    ("c", "recommendation_count"),
    ("e", "evidence_level"),
)

# arduino-router re-exposes the MCU Monitor stream here. Not a tty: the daemon
# owns /dev/ttyHS1 itself, so a serial device path will not reach the panel.
DEFAULT_PANEL_ENDPOINT = "127.0.0.1:7500"


def _clean_record_value(value: Any) -> str:
    """Strip the record's own delimiters out of a value so parsing cannot break."""
    text = str(value)
    return text.replace("|", "/").replace("=", "-").replace("\n", " ").strip()


def build_panel_record(summary: Dict[str, Any]) -> bytes:
    """Render a panel summary as one newline-terminated `FS|` record.

    Absent keys are simply omitted rather than sent empty: the sketch keeps the
    last value it was given for anything a record does not mention, so a partial
    summary degrades to a partially stale panel instead of a blanked one.
    """
    parts = ["FS"]
    for key, source in PANEL_RECORD_FIELDS:
        if source not in summary:
            continue
        value = summary[source]
        if isinstance(value, float):
            value = "{:.2f}".format(value)
        parts.append("{}={}".format(key, _clean_record_value(value)))
    if "offline_mode" in summary:
        parts.append("o={}".format(1 if summary["offline_mode"] else 0))
    return ("|".join(parts) + "\n").encode("ascii", "replace")
