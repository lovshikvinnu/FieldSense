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
    mcu     stream RGB565 to the STM32, which drives the panel over SPI

The `panel` target exists because Chromium is a system asset, not a dependency,
and a stock UNO Q image does not carry one. Without a browser-free path the
board booted to a black screen. `fb` and `png` now fall back to `panel`
automatically when no browser is found, so the display layer degrades instead
of failing. Pass --no-fallback to require the real dashboard render.

No third-party packages. PNG decoding is implemented here against the
standard library so the project keeps `dependencies = []`. The browser and
the fbtft kernel driver are external system assets, exactly like llama.cpp:
discovered at runtime, absent by default, never imported.

The `fb` target needs the panel wired to the QRB2210 SPI bus. On the Arduino
UNO Q it is not, and cannot be: the MPU routes no SPI to the external headers -
D11/D12/D13 and SPI2 land on the STM32U585 only. There is no /dev/fbN for this
panel on that board and no driver can create one. Use `mcu`, which hands the
packed frame to the STM32 over serial and lets it push SPI. See
hardware_test/TFT_UNOQ/frame_receiver/frame_receiver.ino and docs/AI_DEPLOYMENT.md.
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


# ----------------------------------------------------------- MCU frame bridge

# On the Arduino UNO Q the QRB2210 routes no SPI to the external headers -
# D11/D12/D13 and SPI2 land on the STM32U585 only. So the panel can never
# appear as /dev/fbN and `write_framebuffer` has nothing to target. The frame
# has to cross to the MCU, which owns the SPI bus, and be pushed to the
# ST7789 there.
#
# Wire protocol v1. The receiver is hardware_test/TFT_UNOQ/frame_receiver/frame_receiver.ino
# and the two MUST change together.
#
#   Header, 12 bytes, big-endian:
#     [0..1]   magic    0xAA 0xBB
#     [2]      version  0x01
#     [3]      format   0x01 = RGB565 big-endian
#     [4..5]   width    uint16
#     [6..7]   height   uint16
#     [8..9]   chunk    uint16, payload bytes per chunk, always even
#     [10..11] crc16    CCITT-FALSE over bytes [0..9]
#
#   Then ceil(width*height*2 / chunk) chunks, each: payload + crc16 over that
#   payload. The MCU answers ACK or NAK per header and per chunk.
#
# The ACK is load-bearing. The MCU's serial RX buffer is a few hundred bytes
# against a 153,600 byte frame, so each chunk blocks on its ACK. Open-loop
# blasting with a fixed sleep - what the old push_frame.py scratch script did -
# overruns the buffer and shears the image.
#
# RGB565 goes on the wire BIG-endian: that is the order the ST7789 wants, so
# the MCU hands the buffer to writePixels(bigEndian=true) with no byte swap.
# This is deliberately the opposite of the /dev/fbN path, which is little.

FRAME_MAGIC = b"\xaa\xbb"
FRAME_PROTOCOL_VERSION = 0x01
FRAME_FORMAT_RGB565_BE = 0x01
FRAME_HEADER_BYTES = 12

ACK = 0x06
NAK = 0x15

# USB CDC gadget node on the UNO Q. Kept as the default because it is what the
# board exposes without extra device-tree work.
DEFAULT_MCU_PORT = "/dev/ttyGS0"
# Matches LINK_BAUD in the receiver sketch. Raise BOTH together or the link
# desynchronises: 115200 is ~13 s per frame, 921600 is ~1.7 s.
DEFAULT_MCU_BAUD = 115200
# 4 KB keeps the ACK round-trip count to 38 for a full frame and fits the
# receiver's MAX_CHUNK. Must be even - two bytes per pixel.
DEFAULT_CHUNK_BYTES = 4096


def crc16_ccitt(data: bytes) -> int:
    """CRC16 CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no xor-out.

    Mirrors crc16_ccitt() in frame_receiver.ino byte for byte.

    Args:
        data: Bytes to checksum.

    Returns:
        The 16-bit checksum.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def build_frame_header(width: int, height: int, chunk: int) -> bytes:
    """Build the 12-byte frame header the receiver sketch expects.

    Args:
        width: Frame width in pixels.
        height: Frame height in pixels.
        chunk: Payload bytes per chunk. Must be even and fit a uint16.

    Returns:
        The packed header, CRC included.

    Raises:
        DisplayBridgeError: A field does not fit the wire format.
    """
    if not 0 < width <= 0xFFFF or not 0 < height <= 0xFFFF:
        raise DisplayBridgeError(
            "frame geometry {}x{} does not fit the uint16 header fields".format(width, height))
    if chunk <= 0 or chunk > 0xFFFF:
        raise DisplayBridgeError("chunk size {} must be 1..65535 bytes".format(chunk))
    if chunk % 2:
        raise DisplayBridgeError(
            "chunk size {} must be even - RGB565 is two bytes per pixel".format(chunk))

    body = bytearray(FRAME_MAGIC)
    body.append(FRAME_PROTOCOL_VERSION)
    body.append(FRAME_FORMAT_RGB565_BE)
    body += width.to_bytes(2, "big")
    body += height.to_bytes(2, "big")
    body += chunk.to_bytes(2, "big")
    body += crc16_ccitt(bytes(body)).to_bytes(2, "big")
    return bytes(body)


def iter_frame_chunks(payload: bytes, chunk: int) -> List[bytes]:
    """Split a packed frame into on-wire chunks, each with its CRC appended.

    Args:
        payload: Packed RGB565 big-endian frame bytes.
        chunk: Payload bytes per chunk. The final chunk may be short.

    Returns:
        List of chunk records, each payload bytes followed by a 2-byte CRC.
    """
    records = []
    for start in range(0, len(payload), chunk):
        piece = payload[start:start + chunk]
        records.append(piece + crc16_ccitt(piece).to_bytes(2, "big"))
    return records


def _await_ack(transport, what: str, timeout: float) -> None:
    """Block until the MCU answers ACK, raising on NAK, timeout, or garbage.

    Args:
        transport: Open transport exposing read(int) -> bytes.
        what: Label for the error message, e.g. 'header' or 'chunk 7/38'.
        timeout: Seconds already configured on the transport, for the message.

    Raises:
        DisplayBridgeError: NAK, timeout, or an unexpected reply byte.
    """
    reply = transport.read(1)
    if not reply:
        raise DisplayBridgeError(
            "MCU did not acknowledge {} within {}s.\n"
            "Is frame_receiver.ino flashed and running, and does its "
            "LINK_BAUD match --baud?".format(what, timeout))
    if reply[0] == NAK:
        raise DisplayBridgeError(
            "MCU rejected {} (NAK). Geometry, protocol version, or CRC "
            "mismatch - check that the sketch's PANEL_W/PANEL_H and rotation 0 "
            "match the {}x{} frame.".format(what, PANEL_WIDTH, PANEL_HEIGHT))
    if reply[0] != ACK:
        raise DisplayBridgeError(
            "MCU sent unexpected byte 0x{:02x} for {} (wanted ACK 0x06). The "
            "link is out of sync; power-cycle the board and retry.".format(reply[0], what))


def stream_frame_to_mcu(
    payload: bytes,
    width: int,
    height: int,
    port: str = DEFAULT_MCU_PORT,
    baud: int = DEFAULT_MCU_BAUD,
    chunk: int = DEFAULT_CHUNK_BYTES,
    timeout: float = 5.0,
    transport=None,
) -> dict:
    """Stream a packed RGB565 frame to the STM32 and onto the ST7789 panel.

    Args:
        payload: Packed RGB565 BIG-endian bytes, exactly width*height*2 long.
        width: Frame width in pixels.
        height: Frame height in pixels.
        port: Serial device the MCU listens on.
        baud: Line speed. Must equal LINK_BAUD in the receiver sketch.
        chunk: Payload bytes per chunk, even, <= the sketch's MAX_CHUNK.
        timeout: Per-ACK read timeout in seconds.
        transport: Pre-built transport for testing. When None a SerialTransport
            is opened against `port` and closed on the way out.

    Returns:
        Dict with 'bytes', 'chunks', 'port', 'baud', 'chunk_bytes'.

    Raises:
        DisplayBridgeError: Geometry mismatch, transport failure, or the MCU
            did not acknowledge.
    """
    expected = width * height * 2
    if len(payload) != expected:
        raise DisplayBridgeError(
            "payload is {} bytes but {}x{} RGB565 needs {}. Pack with "
            "rgb_to_rgb565(rgb, 'big') before streaming.".format(
                len(payload), width, height, expected))

    header = build_frame_header(width, height, chunk)
    records = iter_frame_chunks(payload, chunk)

    owned = transport is None
    if owned:
        from .transport.serial_port import SerialPortError, SerialTransport

        transport = SerialTransport(port=port, baudrate=baud, timeout=timeout)
        try:
            transport.open()
        except SerialPortError as exc:
            raise DisplayBridgeError(
                "cannot reach the MCU on {}: {}\n"
                "List candidates with:  ls /dev/ttyGS* /dev/ttyACM* /dev/ttyS*".format(port, exc))

    try:
        transport.write(header)
        _await_ack(transport, "header", timeout)

        for index, record in enumerate(records, start=1):
            transport.write(record)
            _await_ack(transport, "chunk {}/{}".format(index, len(records)), timeout)
    except DisplayBridgeError:
        raise
    except Exception as exc:
        raise DisplayBridgeError("MCU stream failed on {}: {}".format(port, exc))
    finally:
        if owned:
            try:
                transport.close()
            except Exception:
                pass

    return {
        "bytes": len(payload),
        "chunks": len(records),
        "port": port,
        "baud": baud,
        "chunk_bytes": chunk,
    }


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
        "--target", default="auto",
        choices=("auto", "probe", "png", "fb", "kiosk", "panel", "mcu"),
        help="auto picks fb, then kiosk, then png (default: auto). "
             "mcu streams the frame to the STM32 over serial - the only path "
             "that reaches the panel on an Arduino UNO Q",
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
    parser.add_argument(
        "--port", default=DEFAULT_MCU_PORT,
        help="serial device the STM32 receiver listens on (--target mcu)",
    )
    parser.add_argument(
        "--baud", type=int, default=DEFAULT_MCU_BAUD,
        help="line speed for --target mcu; must equal LINK_BAUD in the sketch",
    )
    parser.add_argument(
        "--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES,
        help="payload bytes per chunk for --target mcu; even, <= sketch MAX_CHUNK",
    )
    parser.add_argument(
        "--ack-timeout", type=float, default=5.0,
        help="seconds to wait for each MCU ACK (--target mcu)",
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

        # The MCU path owns the SPI bus on the UNO Q, so it resolves before any
        # framebuffer lookup: there is no /dev/fbN for this panel and never
        # will be. Rotation still applies, and the pack is BIG-endian because
        # that is ST7789 wire order - the opposite of the /dev/fbN path.
        if target == "mcu":
            width, height, rgb = rotate_rgb(rgb, width, height, args.rotate)
            payload = rgb_to_rgb565(rgb, "big")
            stats = stream_frame_to_mcu(
                payload, width, height,
                port=args.port, baud=args.baud,
                chunk=args.chunk_bytes, timeout=args.ack_timeout,
            )
            print("streamed {} bytes to {} in {} chunks at {} baud "
                  "({}x{} RGB565-BE, renderer={})".format(
                      stats["bytes"], stats["port"], stats["chunks"],
                      stats["baud"], width, height, renderer))
            return 0

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
