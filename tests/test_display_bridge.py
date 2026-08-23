"""Tests for the 2.8 inch SPI panel display bridge (fieldsense/hardware/display_bridge.py).

All tests here are hardware-free. Tests that need a browser skip cleanly when
none is installed, so the suite stays green on a bare CI machine.
"""

import os
import struct
import zlib

import pytest

from fieldsense.hardware.display_bridge import (
    DisplayBridgeError,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    build_kiosk_command,
    build_parser,
    capture_rgb,
    choose_target,
    crop_rgb,
    decode_png,
    encode_png,
    find_browser,
    framebuffer_info,
    main,
    probe,
    rgb_to_rgb565,
    rotate_rgb,
    write_framebuffer,
)

_MAGIC = b"\x89PNG\r\n\x1a\n"


def _gradient(width, height):
    """Deterministic RGB888 test image."""
    out = bytearray()
    for y in range(height):
        for x in range(width):
            out += bytes([(x * 7) & 0xFF, (y * 11) & 0xFF, (x * y) & 0xFF])
    return bytes(out)


def _png_with_filter(rgb, width, height, filter_type):
    """Encode an RGB888 buffer using one specific PNG filter on every scanline.

    Forward filters are implemented here independently of the decoder, so a
    successful round trip exercises the decoder's unfilter path for real.
    """
    stride = width * 3
    raw = bytearray()
    previous = bytearray(stride)

    for y in range(height):
        line = bytearray(rgb[y * stride:(y + 1) * stride])
        filtered = bytearray(stride)
        for i in range(stride):
            left = line[i - 3] if i >= 3 else 0
            up = previous[i]
            upleft = previous[i - 3] if i >= 3 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) >> 1
            else:  # 4, Paeth
                pa, pb, pc = abs(up - upleft), abs(left - upleft), abs(left + up - 2 * upleft)
                predictor = left if (pa <= pb and pa <= pc) else (up if pb <= pc else upleft)
            filtered[i] = (line[i] - predictor) & 0xFF
        raw.append(filter_type)
        raw += filtered
        previous = line

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">II", width, height) + bytes([8, 2, 0, 0, 0])
    return _MAGIC + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


# ------------------------------------------------------------------ PNG codec


def test_png_round_trip_preserves_pixels():
    """encode_png and decode_png are exact inverses."""
    rgb = _gradient(11, 7)
    width, height, decoded = decode_png(encode_png(rgb, 11, 7))
    assert (width, height) == (11, 7)
    assert decoded == rgb


@pytest.mark.parametrize("filter_type", [0, 1, 2, 3, 4])
def test_png_decode_handles_every_filter_type(filter_type):
    """All five PNG scanline filters unfilter correctly."""
    rgb = _gradient(9, 6)
    width, height, decoded = decode_png(_png_with_filter(rgb, 9, 6, filter_type))
    assert (width, height) == (9, 6)
    assert decoded == rgb, "filter {} decoded incorrectly".format(filter_type)


def test_png_decode_handles_rgba_source():
    """Chromium may emit RGBA; the alpha channel is dropped, not misread."""
    width, height = 4, 3
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw += bytes([x * 10, y * 20, 30, 255])

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = (
        _MAGIC
        + chunk(b"IHDR", struct.pack(">II", width, height) + bytes([8, 6, 0, 0, 0]))
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )
    w, h, rgb = decode_png(png)
    assert (w, h) == (4, 3)
    assert len(rgb) == 4 * 3 * 3
    assert rgb[0:3] == bytes([0, 0, 30])


def test_png_decode_rejects_non_png():
    with pytest.raises(DisplayBridgeError):
        decode_png(b"definitely not a png")


def test_png_decode_rejects_unsupported_variants():
    """A 16-bit PNG is refused explicitly rather than decoded as garbage."""

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = _MAGIC + chunk(b"IHDR", struct.pack(">II", 2, 2) + bytes([16, 2, 0, 0, 0])) + chunk(b"IEND", b"")
    with pytest.raises(DisplayBridgeError):
        decode_png(png)


# ------------------------------------------------------------------ pixel ops


def test_rgb565_packs_known_colours():
    """Red, green, blue and white pack to the documented 16-bit values."""
    rgb = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255])
    packed = rgb_to_rgb565(rgb, "big")
    assert packed[0:2] == b"\xf8\x00"  # red   11111 000000 00000
    assert packed[2:4] == b"\x07\xe0"  # green 00000 111111 00000
    assert packed[4:6] == b"\x00\x1f"  # blue  00000 000000 11111
    assert packed[6:8] == b"\xff\xff"  # white


def test_rgb565_byteorder_is_a_swap():
    """Little-endian output is the big-endian output byte-swapped."""
    rgb = _gradient(4, 4)
    big = rgb_to_rgb565(rgb, "big")
    little = rgb_to_rgb565(rgb, "little")
    assert len(big) == len(little) == 4 * 4 * 2
    assert little == bytes(b for pair in zip(big[1::2], big[0::2]) for b in pair)


def test_rgb565_rejects_bad_byteorder():
    with pytest.raises(DisplayBridgeError):
        rgb_to_rgb565(bytes([0, 0, 0]), "middle")


def test_rgb565_output_size_matches_framebuffer_expectation():
    """A 240x320 panel at 16bpp needs exactly 153600 bytes."""
    rgb = bytes(PANEL_WIDTH * PANEL_HEIGHT * 3)
    assert len(rgb_to_rgb565(rgb)) == PANEL_WIDTH * PANEL_HEIGHT * 2 == 153600


def test_rotation_swaps_dimensions_and_is_reversible():
    """90 degrees swaps axes; four turns return the original."""
    rgb = _gradient(5, 3)
    w, h, once = rotate_rgb(rgb, 5, 3, 90)
    assert (w, h) == (3, 5)

    current, cw, ch = rgb, 5, 3
    for _ in range(4):
        cw, ch, current = rotate_rgb(current, cw, ch, 90)
    assert (cw, ch) == (5, 3)
    assert current == rgb


def test_rotation_180_is_pixel_reversal():
    rgb = _gradient(4, 4)
    w, h, turned = rotate_rgb(rgb, 4, 4, 180)
    assert (w, h) == (4, 4)
    assert turned[0:3] == rgb[-3:]


def test_rotation_zero_is_identity_and_bad_angle_rejected():
    rgb = _gradient(3, 3)
    assert rotate_rgb(rgb, 3, 3, 0) == (3, 3, rgb)
    with pytest.raises(DisplayBridgeError):
        rotate_rgb(rgb, 3, 3, 45)


def test_crop_takes_top_left_region():
    rgb = _gradient(6, 6)
    w, h, cropped = crop_rgb(rgb, 6, 6, 2, 2)
    assert (w, h) == (2, 2)
    assert cropped[0:3] == rgb[0:3]
    assert cropped[3:6] == rgb[3:6]
    assert cropped[6:9] == rgb[6 * 3:6 * 3 + 3]  # start of source row 1


def test_crop_rejects_oversized_request():
    with pytest.raises(DisplayBridgeError):
        crop_rgb(_gradient(2, 2), 2, 2, 5, 5)


# ------------------------------------------------------------------ environment


def test_find_browser_never_raises_on_missing():
    assert find_browser("/nonexistent/browser/binary") is None or isinstance(find_browser(), str)


def test_find_browser_accepts_explicit_executable(tmp_path):
    fake = tmp_path / "chromium"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    assert find_browser(str(fake)) == str(fake)


def test_framebuffer_info_is_safe_on_missing_device():
    info = framebuffer_info("/dev/fb99")
    assert info["device"] == "/dev/fb99"
    assert info["width"] is None and info["height"] is None


def test_write_framebuffer_reports_missing_device():
    with pytest.raises(DisplayBridgeError) as exc:
        write_framebuffer(b"\x00" * 16, "/dev/fb99")
    assert "fbtft" in str(exc.value)


def test_probe_reports_environment_without_side_effects():
    report = probe()
    assert set(report) >= {"platform", "browser", "framebuffers", "display_server", "artifact"}
    assert isinstance(report["framebuffers"], list)


def test_choose_target_respects_explicit_choice():
    assert choose_target("png") == "png"
    assert choose_target("kiosk") == "kiosk"
    assert choose_target("auto") in ("fb", "kiosk", "png")


# ------------------------------------------------------------------ CLI


def test_parser_defaults_to_panel_geometry():
    args = build_parser().parse_args([])
    assert args.width == PANEL_WIDTH and args.height == PANEL_HEIGHT
    assert args.target == "auto"
    assert args.device == "/dev/fb1"
    assert args.byteorder == "little"


def test_parser_accepts_panel_options():
    args = build_parser().parse_args(
        ["--target", "fb", "--device", "/dev/fb0", "--rotate", "90", "--byteorder", "big"]
    )
    assert (args.target, args.device, args.rotate, args.byteorder) == ("fb", "/dev/fb0", 90, "big")


def test_kiosk_command_carries_required_flags(tmp_path):
    fake = tmp_path / "chromium"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    command = build_kiosk_command("artifacts/x.html", 240, 320, str(fake))
    joined = " ".join(command)
    assert "--kiosk" in command
    assert "--window-size=240,320" in command
    assert "--force-device-scale-factor=1" in command
    assert joined.endswith(".html")


def test_main_probe_exits_zero(capsys):
    assert main(["--target", "probe"]) == 0
    assert "display bridge" in capsys.readouterr().out.lower()


def test_main_reports_missing_dashboard_without_raising(capsys):
    code = main(["--target", "png", "--html", "artifacts/does_not_exist.html"])
    assert code == 1
    assert "fieldsense.demo" in capsys.readouterr().err


# ------------------------------------------------------------------ browser path


needs_browser = pytest.mark.skipif(find_browser() is None, reason="no Chromium-family browser installed")


@needs_browser
def test_capture_rgb_renders_exact_panel_geometry(tmp_path):
    """End-to-end: the dashboard renders at exactly 240x320 CSS pixels.

    Guards the iframe wrapper. Chromium clamps headless windows to a minimum
    width, so a naive --window-size=240 silently produces the wider tablet
    layout cropped to 240px. A correct compact render keeps the header on one
    row, which places the dashboard background at the top-left corner.
    """
    html = "artifacts/fieldsense_competition_demo.html"
    if not os.path.isfile(html):
        pytest.skip("dashboard artifact not built")

    width, height, rgb = capture_rgb(html, PANEL_WIDTH, PANEL_HEIGHT, settle_ms=1200)

    assert (width, height) == (PANEL_WIDTH, PANEL_HEIGHT)
    assert len(rgb) == PANEL_WIDTH * PANEL_HEIGHT * 3
    assert rgb[0:3] == bytes([0x0F, 0x17, 0x2A]), "top-left is not the dashboard background"
    assert len({rgb[i * 3:i * 3 + 3] for i in range(width * height)}) > 50, "frame looks blank"


@needs_browser
def test_captured_frame_packs_to_exact_framebuffer_size():
    """The captured frame is exactly one 240x320 RGB565 framebuffer write."""
    html = "artifacts/fieldsense_competition_demo.html"
    if not os.path.isfile(html):
        pytest.skip("dashboard artifact not built")

    width, height, rgb = capture_rgb(html, PANEL_WIDTH, PANEL_HEIGHT, settle_ms=1200)
    assert len(rgb_to_rgb565(rgb)) == 153600
