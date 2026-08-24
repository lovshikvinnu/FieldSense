"""Display bridge - render the offline dashboard onto the 2.8 inch SPI panel.

The dashboard is a self-contained HTML document. The panel is a 240x320
ST7789V SPI display. This module joins the two on the Linux (QRB2210) side.

    artifacts/*.html
          |
          |  headless browser, 240x320 viewport
          v
      PNG bytes
          |
          |  stdlib PNG decode (zlib), optional rotation
          v
      RGB888 buffer
          |
          |  RGB565 pack
          v
    /dev/fbN  (fbtft driver exposes the SPI panel as a framebuffer)

Five targets:

    probe   report what this machine can do, change nothing
    png     write a 240x320 PNG   (works anywhere a browser exists)
    fb      write RGB565 to a framebuffer device   (the panel)
    kiosk   launch a full-screen browser   (needs a display server)
    panel   draw the status panel WITHOUT a browser   (see panel_renderer)

The `panel` target exists because Chromium is a system asset, not a dependency,
and a stock UNO Q image does not carry one. Without a browser-free path the
board booted to a black screen. `fb` and `png` now fall back to `panel`
automatically when no browser is found, so the display layer degrades instead
of failing. Pass --no-fallback to require the real dashboard render.

No third-party packages. PNG decoding is implemented here against the
standard library so the project keeps `dependencies = []`. The browser and
the fbtft kernel driver are external system assets, exactly like llama.cpp:
discovered at runtime, absent by default, never imported.

HARDWARE_SPEC_REQUIRED - the panel must be wired to the QRB2210 SPI bus for
the `fb` target to have anything to write to. Bench verification to date used
the STM32 MCU. See docs/AI_DEPLOYMENT.md.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zlib
from typing import List, Optional, Tuple

PANEL_WIDTH = 240
PANEL_HEIGHT = 320
DEFAULT_HTML = "artifacts/fieldsense_competition_demo.html"

# Checked in order. The first one present wins.
BROWSER_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    "/usr/lib/chromium/chromium",
    "/snap/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class DisplayBridgeError(Exception):
    """Raised when the bridge cannot complete a requested operation."""


# --------------------------------------------------------------- environment


def find_browser(explicit: Optional[str] = None) -> Optional[str]:
    """Locate a Chromium-family browser binary.

    Args:
        explicit: Caller-supplied path, tried first.

    Returns:
        Path to an executable browser, or None. Never raises.
    """
    candidates: List[str] = ([explicit] if explicit else []) + list(BROWSER_CANDIDATES)
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


def list_framebuffers() -> List[str]:
    """Return framebuffer device paths present on this machine."""
    return sorted(
        "/dev/" + name
        for name in os.listdir("/dev")
        if name.startswith("fb") and name[2:].isdigit()
    ) if os.path.isdir("/dev") else []


# Preference order when no device is named. fb1 first because an fbtft SPI
# panel usually enumerates behind whatever the SoC already registered, but a
# board where the panel is the ONLY framebuffer exposes it as fb0.
FRAMEBUFFER_CANDIDATES = ("/dev/fb1", "/dev/fb0")


def detect_framebuffer(explicit: Optional[str] = None) -> Optional[str]:
    """Return the framebuffer device to write to, or None if there is none.

    Args:
        explicit: Caller-supplied device, returned as-is when given.

    Returns:
        First existing device from FRAMEBUFFER_CANDIDATES, then any other
        /dev/fbN present, otherwise None. Never raises.

    Why this exists: `choose_target('auto')` used to select the `fb` target if
    EITHER fb1 or fb0 existed, while the write always went to the `--device`
    default of /dev/fb1. On a board whose panel is fb0 — the common case when
    the panel is the only framebuffer — auto-detection therefore chose `fb`
    and then wrote to a device that did not exist.
    """
    if explicit:
        return explicit
    for candidate in FRAMEBUFFER_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    remaining = [fb for fb in list_framebuffers() if fb not in FRAMEBUFFER_CANDIDATES]
    return remaining[0] if remaining else None


def framebuffer_info(device: str) -> dict:
    """Read geometry and colour depth for a framebuffer device.

    Args:
        device: Path such as '/dev/fb1'.

    Returns:
        Dict with 'width', 'height', 'bpp' where readable, plus 'device'.
        Missing values are None rather than an exception, so probing a
        machine without the driver loaded stays safe.
    """
    name = os.path.basename(device)
    base = "/sys/class/graphics/{}".format(name)
    info = {"device": device, "width": None, "height": None, "bpp": None}

    try:
        with open(os.path.join(base, "virtual_size"), "r") as handle:
            width, height = handle.read().strip().split(",")
            info["width"], info["height"] = int(width), int(height)
    except (OSError, ValueError):
        pass

    try:
        with open(os.path.join(base, "bits_per_pixel"), "r") as handle:
            info["bpp"] = int(handle.read().strip())
    except (OSError, ValueError):
        pass

    return info


# --------------------------------------------------------------- PNG decoding


def decode_png(data: bytes) -> Tuple[int, int, bytes]:
    """Decode an 8-bit RGB or RGBA PNG into a flat RGB888 buffer.

    Implemented against the standard library only. Chromium screenshots are
    non-interlaced 8-bit RGB/RGBA, which is the subset handled here.

    Args:
        data: Complete PNG file bytes.

    Returns:
        Tuple of (width, height, rgb_bytes) with len(rgb_bytes) == w * h * 3.

    Raises:
        DisplayBridgeError: Not a PNG, or an unsupported PNG variant.
    """
    if data[:8] != _PNG_MAGIC:
        raise DisplayBridgeError("not a PNG file")

    pos = 8
    width = height = bitdepth = colortype = interlace = None
    idat = bytearray()

    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length  # length + type + data + crc

        if ctype == b"IHDR":
            width = int.from_bytes(chunk[0:4], "big")
            height = int.from_bytes(chunk[4:8], "big")
            bitdepth, colortype, interlace = chunk[8], chunk[9], chunk[12]
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break

    if width is None or height is None:
        raise DisplayBridgeError("PNG has no IHDR chunk")
    if bitdepth != 8:
        raise DisplayBridgeError("unsupported PNG bit depth {}".format(bitdepth))
    if colortype not in (2, 6):
        raise DisplayBridgeError("unsupported PNG colour type {}".format(colortype))
    if interlace != 0:
        raise DisplayBridgeError("interlaced PNG is not supported")

    channels = 3 if colortype == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    expected = (stride + 1) * height
    if len(raw) < expected:
        raise DisplayBridgeError("truncated PNG image data")

    out = bytearray(width * height * 3)
    previous = bytearray(stride)
    read = 0
    write = 0

    for _ in range(height):
        filter_type = raw[read]
        read += 1
        line = bytearray(raw[read:read + stride])
        read += stride

        if filter_type == 1:  # Sub
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filter_type == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif filter_type == 3:  # Average
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif filter_type == 4:  # Paeth
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                up = previous[i]
                upleft = previous[i - channels] if i >= channels else 0
                pa = abs(up - upleft)
                pb = abs(left - upleft)
                pc = abs(left + up - 2 * upleft)
                if pa <= pb and pa <= pc:
                    predictor = left
                elif pb <= pc:
                    predictor = up
                else:
                    predictor = upleft
                line[i] = (line[i] + predictor) & 0xFF
        elif filter_type != 0:
            raise DisplayBridgeError("unknown PNG filter type {}".format(filter_type))

        for x in range(width):
            src = x * channels
            out[write] = line[src]
            out[write + 1] = line[src + 1]
            out[write + 2] = line[src + 2]
            write += 3

        previous = line

    return width, height, bytes(out)


def encode_png(rgb: bytes, width: int, height: int) -> bytes:
    """Encode a flat RGB888 buffer as an 8-bit RGB PNG.

    Standard library only (zlib for compression, zlib.crc32 for chunk CRCs).

    Args:
        rgb: Flat RGB888 buffer of width * height * 3 bytes.
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        Complete PNG file bytes.
    """
    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return (
            len(payload).to_bytes(4, "big")
            + body
            + (zlib.crc32(body) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes([8, 2, 0, 0, 0])  # 8-bit, truecolour RGB, no interlace
    )
    return (
        _PNG_MAGIC
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


def crop_rgb(
    rgb: bytes, width: int, height: int, crop_w: int, crop_h: int
) -> Tuple[int, int, bytes]:
    """Crop the top-left region out of an RGB888 buffer.

    Args:
        rgb: Flat RGB888 buffer.
        width: Source width.
        height: Source height.
        crop_w: Target width.
        crop_h: Target height.

    Returns:
        Tuple of (crop_w, crop_h, cropped_rgb).

    Raises:
        DisplayBridgeError: Requested crop is larger than the source.
    """
    if crop_w > width or crop_h > height:
        raise DisplayBridgeError(
            "cannot crop {}x{} out of {}x{}".format(crop_w, crop_h, width, height)
        )
    if crop_w == width and crop_h == height:
        return width, height, rgb

    out = bytearray(crop_w * crop_h * 3)
    row = crop_w * 3
    for y in range(crop_h):
        src = (y * width) * 3
        out[y * row:(y + 1) * row] = rgb[src:src + row]
    return crop_w, crop_h, bytes(out)


# --------------------------------------------------------------- pixel output


def rotate_rgb(rgb: bytes, width: int, height: int, degrees: int) -> Tuple[int, int, bytes]:
    """Rotate an RGB888 buffer clockwise by 0, 90, 180 or 270 degrees.

    Args:
        rgb: Flat RGB888 buffer.
        width: Source width in pixels.
        height: Source height in pixels.
        degrees: One of 0, 90, 180, 270.

    Returns:
        Tuple of (new_width, new_height, rotated_rgb).
    """
    if degrees % 360 == 0:
        return width, height, rgb
    if degrees not in (90, 180, 270):
        raise DisplayBridgeError("rotation must be 0, 90, 180 or 270")

    out = bytearray(len(rgb))
    if degrees == 180:
        new_w, new_h = width, height
        for y in range(height):
            for x in range(width):
                src = (y * width + x) * 3
                dst = ((height - 1 - y) * width + (width - 1 - x)) * 3
                out[dst:dst + 3] = rgb[src:src + 3]
    else:
        new_w, new_h = height, width
        for y in range(height):
            for x in range(width):
                src = (y * width + x) * 3
                if degrees == 90:
                    nx, ny = height - 1 - y, x
                else:  # 270
                    nx, ny = y, width - 1 - x
                dst = (ny * new_w + nx) * 3
                out[dst:dst + 3] = rgb[src:src + 3]

    return new_w, new_h, bytes(out)


def rgb_to_rgb565(rgb: bytes, byteorder: str = "little") -> bytes:
    """Pack an RGB888 buffer into 16-bit RGB565.

    Linux framebuffers in RGB565 are little-endian. A raw ST7789V SPI stream
    expects big-endian (most significant byte first), hence the switch.

    Args:
        rgb: Flat RGB888 buffer.
        byteorder: 'little' for /dev/fbN, 'big' for direct SPI.

    Returns:
        Packed RGB565 bytes, two per pixel.
    """
    if byteorder not in ("little", "big"):
        raise DisplayBridgeError("byteorder must be 'little' or 'big'")

    pixels = len(rgb) // 3
    out = bytearray(pixels * 2)
    little = byteorder == "little"

    for i in range(pixels):
        red, green, blue = rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]
        value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        if little:
            out[i * 2] = value & 0xFF
            out[i * 2 + 1] = value >> 8
        else:
            out[i * 2] = value >> 8
            out[i * 2 + 1] = value & 0xFF

    return bytes(out)


# --------------------------------------------------------------- browser


# Chromium clamps a headless window to a minimum width (500px observed).
# Asking for --window-size=240,320 therefore yields a 500px CSS viewport, the
# >=480px media query fires, and the tablet layout is silently cropped to
# 240x320 - a wrong render that still has the right dimensions.
#
# Fix: host the dashboard in an exactly-sized iframe pinned to the top-left of
# a comfortably large page. An iframe gets its OWN viewport, so the compact
# media queries evaluate against 240px as they do on the panel. The screenshot
# is then cropped back to the iframe.
_MIN_WINDOW = 640

_WRAPPER = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  html,body{{margin:0;padding:0;background:#0f172a;overflow:hidden}}
  iframe{{position:fixed;top:0;left:0;width:{w}px;height:{h}px;border:0;display:block}}
</style></head>
<body><iframe src="{url}" scrolling="no"></iframe></body></html>
"""


def capture_rgb(
    html_path: str,
    width: int = PANEL_WIDTH,
    height: int = PANEL_HEIGHT,
    browser: Optional[str] = None,
    timeout: float = 60.0,
    settle_ms: int = 800,
) -> Tuple[int, int, bytes]:
    """Render an HTML file at an exact CSS viewport and return RGB888 pixels.

    Args:
        html_path: Path to the dashboard HTML.
        width: CSS viewport width in pixels.
        height: CSS viewport height in pixels.
        browser: Optional explicit browser binary.
        timeout: Seconds before the render is abandoned.
        settle_ms: Virtual time budget, so page scripts finish painting.

    Returns:
        Tuple of (width, height, rgb888).

    Raises:
        DisplayBridgeError: No browser, missing HTML, or render failure.
    """
    if not os.path.isfile(html_path):
        raise DisplayBridgeError(
            "dashboard not found: {}\nGenerate it with:  python3 -m fieldsense.demo".format(html_path)
        )

    binary = find_browser(browser)
    if binary is None:
        raise DisplayBridgeError(
            "no Chromium-family browser found. Install one with:\n"
            "  sudo apt install chromium"
        )

    window_w = max(width, _MIN_WINDOW)
    window_h = max(height, _MIN_WINDOW)
    url = "file://" + os.path.abspath(html_path)

    with tempfile.TemporaryDirectory() as workdir:
        wrapper = os.path.join(workdir, "wrapper.html")
        with open(wrapper, "w", encoding="utf-8") as handle:
            handle.write(_WRAPPER.format(w=width, h=height, url=url))

        shot = os.path.join(workdir, "frame.png")
        command = [
            binary,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--default-background-color=0f172a",
            "--allow-file-access-from-files",
            "--virtual-time-budget={}".format(settle_ms),
            "--window-size={},{}".format(window_w, window_h),
            "--screenshot=" + shot,
            "file://" + wrapper,
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            raise DisplayBridgeError("browser render timed out after {}s".format(timeout))
        except OSError as exc:
            raise DisplayBridgeError("could not execute browser: {}".format(exc))

        if not os.path.isfile(shot):
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else "no output"
            raise DisplayBridgeError("browser produced no screenshot ({})".format(tail))

        with open(shot, "rb") as handle:
            png = handle.read()

    shot_w, shot_h, rgb = decode_png(png)
    return crop_rgb(rgb, shot_w, shot_h, width, height)


def capture_or_panel(
    html_path: str,
    width: int = PANEL_WIDTH,
    height: int = PANEL_HEIGHT,
    browser: Optional[str] = None,
    timeout: float = 60.0,
    settle_ms: int = 800,
    allow_fallback: bool = True,
    summary_path: Optional[str] = None,
) -> Tuple[int, int, bytes, str]:
    """Render the dashboard, falling back to the browser-free status panel.

    Args:
        html_path: Dashboard HTML to rasterise.
        width: Frame width in pixels.
        height: Frame height in pixels.
        browser: Optional explicit browser binary.
        timeout: Render timeout in seconds.
        settle_ms: Paint settle budget in milliseconds.
        allow_fallback: When False, a failed browser render raises instead of
            degrading, which is what a bench check of the real UI wants.
        summary_path: Panel summary JSON. Defaults to the pipeline's own.

    Returns:
        Tuple of (width, height, rgb888, renderer) where renderer is
        'dashboard' or 'panel'.

    Raises:
        DisplayBridgeError: Rendering failed and fallback was not allowed.
    """
    from . import panel_renderer

    try:
        rendered_w, rendered_h, rgb = capture_rgb(
            html_path, width, height, browser, timeout, settle_ms
        )
        return rendered_w, rendered_h, rgb, "dashboard"
    except DisplayBridgeError as exc:
        if not allow_fallback:
            raise
        reason = str(exc).splitlines()[0].rstrip(" :")

    summary = panel_renderer.load_panel_summary(
        summary_path or panel_renderer.PANEL_SUMMARY_PATH
    )
    if summary is None:
        summary = panel_renderer.placeholder_summary("RUN FIELDSENSE.DEMO")
    else:
        summary = dict(summary)
        summary.setdefault("panel_note", "TEXT PANEL")

    print("display bridge: {} - drawing the browser-free status panel".format(reason),
          file=sys.stderr)
    panel_w, panel_h, rgb = panel_renderer.render_summary_panel(summary, width, height)
    return panel_w, panel_h, rgb, "panel"


def build_kiosk_command(
    html_path: str,
    width: int = PANEL_WIDTH,
    height: int = PANEL_HEIGHT,
    browser: Optional[str] = None,
) -> List[str]:
    """Assemble the full-screen kiosk browser command.

    Args:
        html_path: Path to the dashboard HTML.
        width: Window width in pixels.
        height: Window height in pixels.
        browser: Optional explicit browser binary.

    Returns:
        Argument vector ready for subprocess.
    """
    binary = find_browser(browser)
    if binary is None:
        raise DisplayBridgeError("no Chromium-family browser found")

    return [
        binary,
        "--kiosk",
        "--incognito",
        "--noerrdialogs",
        "--disable-infobars",
        "--disable-session-crashed-bubble",
        "--disable-translate",
        "--disable-pinch",
        "--overscroll-history-navigation=0",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--check-for-update-interval=31536000",
        "--window-position=0,0",
        "--window-size={},{}".format(width, height),
        "--app=file://" + os.path.abspath(html_path),
    ]


# --------------------------------------------------------------- targets


def write_framebuffer(
    payload: bytes, device: str, geometry: Optional[Tuple[int, int]] = None
) -> int:
    """Write a packed pixel buffer to a framebuffer device.

    Args:
        payload: Packed RGB565 bytes.
        device: Framebuffer device path.
        geometry: Optional (width, height) of the frame, checked against the
            panel's reported geometry so a rotated frame cannot be written
            transposed.

    Returns:
        Number of bytes written.

    Raises:
        DisplayBridgeError: Device missing, not writable, or size mismatch.
    """
    if not os.path.exists(device):
        raise DisplayBridgeError(
            "framebuffer {} does not exist. Is the fbtft driver loaded?\n"
            "Check with:  ls /dev/fb*   and   dmesg | grep -i fb".format(device)
        )

    info = framebuffer_info(device)
    if info["width"] and info["height"] and info["bpp"]:
        expected = info["width"] * info["height"] * (info["bpp"] // 8)
        # Geometry, not just byte count. A 90 or 270 degree rotation of a
        # 240x320 frame yields 320x240, which has the SAME byte count and would
        # pass a size-only check while writing a transposed image to the panel.
        if geometry is not None and tuple(geometry) != (info["width"], info["height"]):
            raise DisplayBridgeError(
                "geometry mismatch: {} is {}x{}, frame is {}x{}.\n"
                "Byte counts happen to match, so this would display transposed. "
                "Adjust --rotate / --width / --height.".format(
                    device, info["width"], info["height"], geometry[0], geometry[1]
                )
            )
        if expected != len(payload):
            raise DisplayBridgeError(
                "size mismatch: {} expects {}x{} at {}bpp = {} bytes, got {} bytes.\n"
                "Adjust --width/--height/--rotate to match the panel.".format(
                    device, info["width"], info["height"], info["bpp"], expected, len(payload)
                )
            )

    try:
        with open(device, "wb") as handle:
            written = handle.write(payload)
            handle.flush()
        return written
    except PermissionError:
        raise DisplayBridgeError(
            "permission denied writing {}. Add yourself to the 'video' group:\n"
            "  sudo usermod -aG video $USER   (then log out and back in)".format(device)
        )
    except OSError as exc:
        raise DisplayBridgeError("could not write {}: {}".format(device, exc))


def probe() -> dict:
    """Report what this machine can do, without changing anything.

    Returns:
        Dict describing browser, framebuffers, display server and artifact.
    """
    from . import panel_renderer

    framebuffers = list_framebuffers()
    browser = find_browser()
    return {
        "platform": sys.platform,
        "browser": browser,
        "framebuffers": [framebuffer_info(fb) for fb in framebuffers],
        "framebuffer_selected": detect_framebuffer(),
        "display_server": os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"),
        "artifact": DEFAULT_HTML if os.path.isfile(DEFAULT_HTML) else None,
        "panel_summary": panel_renderer.PANEL_SUMMARY_PATH
        if os.path.isfile(panel_renderer.PANEL_SUMMARY_PATH) else None,
        "renderer": "dashboard" if browser else "panel (no browser; browser-free fallback)",
    }


def choose_target(requested: str) -> str:
    """Resolve the 'auto' target against the current environment."""
    if requested != "auto":
        return requested
    if detect_framebuffer() is not None:
        return "fb"
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return "kiosk"
    return "png"


# --------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    """Construct the command line parser."""
    parser = argparse.ArgumentParser(
        prog="python3 -m fieldsense.hardware.display_bridge",
        description="Render the FieldSense dashboard onto the 2.8 inch SPI panel.",
    )
    parser.add_argument(
        "--target", default="auto", choices=("auto", "probe", "png", "fb", "kiosk", "panel"),
        help="auto picks fb, then kiosk, then png (default: auto)",
    )
    parser.add_argument("--html", default=DEFAULT_HTML, help="dashboard HTML to display")
    parser.add_argument(
        "--device", default="auto",
        help="framebuffer device for --target fb; 'auto' detects fb1 then fb0",
    )
    parser.add_argument("--out", default="artifacts/panel_frame.png", help="output path for --target png")
    parser.add_argument("--width", type=int, default=PANEL_WIDTH, help="viewport width")
    parser.add_argument("--height", type=int, default=PANEL_HEIGHT, help="viewport height")
    parser.add_argument(
        "--rotate", type=int, default=0, choices=(0, 90, 180, 270),
        help="clockwise rotation applied after capture",
    )
    parser.add_argument(
        "--byteorder", default="little", choices=("little", "big"),
        help="little for /dev/fbN, big for a raw SPI stream",
    )
    parser.add_argument("--browser", default=None, help="explicit browser binary")
    parser.add_argument("--settle-ms", type=int, default=800, help="paint delay before capture")
    parser.add_argument("--timeout", type=float, default=60.0, help="render timeout in seconds")
    parser.add_argument(
        "--no-fallback", action="store_true",
        help="fail instead of drawing the browser-free status panel",
    )
    parser.add_argument(
        "--summary", default=None,
        help="panel summary JSON for the browser-free renderer",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point. Returns a process exit code and never raises."""
    args = build_parser().parse_args(argv)

    try:
        target = choose_target(args.target)

        if target == "probe":
            report = probe()
            print("FieldSense display bridge - environment probe\n")
            print("  platform        : {}".format(report["platform"]))
            print("  browser         : {}".format(report["browser"] or "NOT FOUND"))
            print("  renderer        : {}".format(report["renderer"]))
            print("  display server  : {}".format(report["display_server"] or "none"))
            print("  dashboard       : {}".format(report["artifact"] or "NOT BUILT"))
            print("  panel summary   : {}".format(report["panel_summary"] or "NOT BUILT"))
            if report["framebuffers"]:
                for fb in report["framebuffers"]:
                    print("  framebuffer     : {} {}x{} @ {}bpp".format(
                        fb["device"], fb["width"], fb["height"], fb["bpp"]))
            else:
                print("  framebuffer     : none (fbtft driver not loaded)")
            print("  selected fb     : {}".format(report["framebuffer_selected"] or "none"))
            print("\n  would use target: {}".format(choose_target("auto")))
            return 0

        if target == "kiosk":
            command = build_kiosk_command(args.html, args.width, args.height, args.browser)
            if not os.path.isfile(args.html):
                raise DisplayBridgeError(
                    "dashboard not found: {}\nGenerate it with:  python3 -m fieldsense.demo".format(args.html))
            print("launching kiosk: {}".format(" ".join(command[:2])))
            os.execv(command[0], command)  # replace this process; never returns
            return 0

        if target == "panel":
            from . import panel_renderer

            summary = panel_renderer.load_panel_summary(
                args.summary or panel_renderer.PANEL_SUMMARY_PATH
            ) or panel_renderer.placeholder_summary("RUN FIELDSENSE.DEMO")
            width, height, rgb = panel_renderer.render_summary_panel(
                summary, args.width, args.height
            )
            renderer = "panel"
        else:
            width, height, rgb, renderer = capture_or_panel(
                args.html, args.width, args.height, args.browser, args.timeout,
                args.settle_ms, allow_fallback=not args.no_fallback,
                summary_path=args.summary,
            )

        device = detect_framebuffer(None if args.device == "auto" else args.device)

        # `panel` says HOW to draw, not WHERE to send it, so it resolves its
        # destination the same way `auto` does: the framebuffer when one exists,
        # a PNG otherwise. That keeps it usable on a laptop for verification.
        if target == "png" or (target == "panel" and device is None):
            out_dir = os.path.dirname(args.out)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            png = encode_png(rgb, width, height)
            with open(args.out, "wb") as handle:
                handle.write(png)
            print("wrote {} ({}x{}, {} bytes, renderer={})".format(
                args.out, width, height, len(png), renderer))
            return 0

        # target == "fb" or "panel" with a framebuffer present
        if device is None:
            raise DisplayBridgeError(
                "no framebuffer device found (looked for {}). Is the fbtft driver "
                "loaded?\nCheck with:  ls /dev/fb*   and   dmesg | grep -i fb".format(
                    ", ".join(FRAMEBUFFER_CANDIDATES))
            )

        width, height, rgb = rotate_rgb(rgb, width, height, args.rotate)
        payload = rgb_to_rgb565(rgb, args.byteorder)
        written = write_framebuffer(payload, device, geometry=(width, height))
        print("wrote {} bytes to {} ({}x{} RGB565, renderer={})".format(
            written, device, width, height, renderer))
        return 0

    except DisplayBridgeError as exc:
        print("display bridge: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
