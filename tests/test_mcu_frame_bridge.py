"""Tests for the MCU frame bridge - the serial path to the ST7789 panel.

On the Arduino UNO Q the QRB2210 routes no SPI to the external headers, so
/dev/fbN can never reach this panel and the frame has to cross to the STM32.
These tests guard the wire protocol shared with
hardware_test/TFT_UNOQ/frame_receiver/frame_receiver.ino.

The MockSTM32 below parses the byte stream from the protocol SPEC rather than
by calling the production helpers, so agreement between the two is real
evidence and not a tautology. If you change the protocol on one side, these
tests fail until you change the other.

All hardware-free: no serial device is opened. The TCP transport tests bind a
loopback listener on an ephemeral port and talk to themselves - no board, no
arduino-router, no fixed port to collide with.
"""

import time

import pytest

from fieldsense.hardware.display_bridge import (
    ACK,
    DEFAULT_CHUNK_BYTES,
    DEFAULT_MCU_BAUD,
    DEFAULT_MCU_PORT,
    FRAME_FORMAT_RGB565_BE,
    FRAME_HEADER_BYTES,
    FRAME_MAGIC,
    FRAME_PROTOCOL_VERSION,
    NAK,
    DisplayBridgeError,
    build_frame_header,
    build_parser,
    crc16_ccitt,
    iter_frame_chunks,
    rgb_to_rgb565,
    stream_frame_to_mcu,
)
from fieldsense.hardware.transport.tcp_socket import (
    TcpTransport,
    TcpTransportError,
    parse_endpoint,
)

PANEL_W, PANEL_H = 240, 320
FRAME_BYTES = PANEL_W * PANEL_H * 2


def crc_reference(data: bytes) -> int:
    """CRC16/CCITT-FALSE written independently of the production helper."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def gradient_frame() -> bytes:
    """A packed RGB565-BE frame with structure in every axis.

    Deliberately not a flat fill: a solid colour hides byte-order errors,
    chunk-boundary drift, and off-by-one geometry all at once.
    """
    rgb = bytearray()
    for y in range(PANEL_H):
        for x in range(PANEL_W):
            rgb += bytes((
                (x * 255) // (PANEL_W - 1),
                (y * 255) // (PANEL_H - 1),
                ((x + y) * 255) // (PANEL_W + PANEL_H - 2),
            ))
    return rgb_to_rgb565(bytes(rgb), "big")


class MockSTM32:
    """Byte-level stand-in for frame_receiver.ino.

    Mirrors the sketch's state machine: hunt for magic, validate the header
    CRC and geometry, then per chunk validate the CRC and ACK. Records the
    pixel bytes it would have handed to writePixels().
    """

    def __init__(self, panel_w=PANEL_W, panel_h=PANEL_H, max_chunk=DEFAULT_CHUNK_BYTES):
        self.panel_w = panel_w
        self.panel_h = panel_h
        self.max_chunk = max_chunk
        self.inbox = bytearray()
        self.replies = bytearray()
        self.pixels = bytearray()
        self.state = "sync"
        self.chunk = 0
        self.total = 0
        self.nak_reason = None
        self.closed = False

    # ---------------------------------------------------- transport surface

    def write(self, payload: bytes) -> None:
        self.inbox += payload
        self._pump()

    def read(self, length: int = 1) -> bytes:
        out = bytes(self.replies[:length])
        self.replies = self.replies[length:]
        return out

    def close(self) -> None:
        self.closed = True

    # ---------------------------------------------------- sketch state machine

    def _pump(self) -> None:
        while True:
            if self.state == "sync":
                index = self.inbox.find(FRAME_MAGIC)
                if index < 0:
                    return
                del self.inbox[:index + 2]
                self.state = "header"

            if self.state == "header":
                if len(self.inbox) < FRAME_HEADER_BYTES - 2:
                    return
                rest = bytes(self.inbox[:10])
                del self.inbox[:10]
                header = FRAME_MAGIC + rest

                if crc_reference(header[:10]) != int.from_bytes(header[10:12], "big"):
                    self._nak("header crc")
                    continue

                width = int.from_bytes(header[4:6], "big")
                height = int.from_bytes(header[6:8], "big")
                self.chunk = int.from_bytes(header[8:10], "big")

                acceptable = (
                    header[2] == FRAME_PROTOCOL_VERSION
                    and header[3] == FRAME_FORMAT_RGB565_BE
                    and width == self.panel_w
                    and height == self.panel_h
                    and 0 < self.chunk <= self.max_chunk
                    and self.chunk % 2 == 0
                    # Whole rows only - the sketch sets an address window per
                    # chunk from the row index and cannot express a mid-row
                    # boundary. Mirrors the guard in frame_receiver.ino.
                    and self.chunk % (width * 2) == 0
                )
                if not acceptable:
                    self._nak("geometry or protocol")
                    continue

                self.total = width * height * 2
                self.replies.append(ACK)
                self.state = "chunks"

            if self.state == "chunks":
                if len(self.pixels) >= self.total:
                    self.state = "done"
                    return
                want = min(self.chunk, self.total - len(self.pixels))
                if len(self.inbox) < want + 2:
                    return
                body = bytes(self.inbox[:want])
                crc = int.from_bytes(self.inbox[want:want + 2], "big")
                del self.inbox[:want + 2]
                if crc_reference(body) != crc:
                    self._nak("chunk crc")
                    continue
                self.pixels += body
                self.replies.append(ACK)
                continue

            return

    def _nak(self, reason: str) -> None:
        self.replies.append(NAK)
        self.nak_reason = reason
        self.state = "sync"


# ------------------------------------------------------------------- CRC


def test_crc16_matches_published_ccitt_false_vector():
    """CCITT-FALSE of '123456789' is 0x29B1. Pins the variant, not just a hash."""
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_crc16_agrees_with_independent_reference():
    for length in range(0, 300, 7):
        payload = bytes((i * 31 + 7) & 0xFF for i in range(length))
        assert crc16_ccitt(payload) == crc_reference(payload)


def test_crc16_of_empty_input_is_init_value():
    assert crc16_ccitt(b"") == 0xFFFF


# ------------------------------------------------------------------- header


def test_header_layout_is_exactly_what_the_sketch_parses():
    header = build_frame_header(PANEL_W, PANEL_H, DEFAULT_CHUNK_BYTES)
    assert len(header) == FRAME_HEADER_BYTES
    assert header[:2] == FRAME_MAGIC
    assert header[2] == FRAME_PROTOCOL_VERSION
    assert header[3] == FRAME_FORMAT_RGB565_BE
    assert int.from_bytes(header[4:6], "big") == PANEL_W
    assert int.from_bytes(header[6:8], "big") == PANEL_H
    assert int.from_bytes(header[8:10], "big") == DEFAULT_CHUNK_BYTES
    assert int.from_bytes(header[10:12], "big") == crc_reference(header[:10])


@pytest.mark.parametrize("chunk", [0, 4095, 70000, -2])
def test_header_rejects_unusable_chunk_sizes(chunk):
    """Odd chunks split a pixel across a frame boundary; the sketch NAKs them."""
    with pytest.raises(DisplayBridgeError):
        build_frame_header(PANEL_W, PANEL_H, chunk)


@pytest.mark.parametrize("width,height", [(0, 320), (240, 0), (70000, 320)])
def test_header_rejects_geometry_outside_uint16(width, height):
    with pytest.raises(DisplayBridgeError):
        build_frame_header(width, height, DEFAULT_CHUNK_BYTES)


# ------------------------------------------------------------------- chunking


def test_chunking_covers_the_frame_exactly_once():
    payload = gradient_frame()
    records = iter_frame_chunks(payload, DEFAULT_CHUNK_BYTES)
    assert len(records) == 40  # ceil(153600 / 3840), 8 rows per chunk
    rebuilt = b"".join(record[:-2] for record in records)
    assert rebuilt == payload


def test_each_chunk_carries_a_valid_trailing_crc():
    for record in iter_frame_chunks(gradient_frame(), DEFAULT_CHUNK_BYTES):
        body, crc = record[:-2], int.from_bytes(record[-2:], "big")
        assert crc_reference(body) == crc


def test_final_chunk_is_short_when_the_frame_does_not_divide_evenly():
    records = iter_frame_chunks(b"\x00" * 1000, 384)
    assert [len(r) - 2 for r in records] == [384, 384, 232]


# ------------------------------------------------------------------- streaming


def test_full_frame_arrives_byte_identical():
    payload = gradient_frame()
    mcu = MockSTM32()
    stats = stream_frame_to_mcu(payload, PANEL_W, PANEL_H, transport=mcu)

    assert bytes(mcu.pixels) == payload
    assert mcu.nak_reason is None
    assert stats["bytes"] == FRAME_BYTES
    assert stats["chunks"] == 40


def test_caller_supplied_transport_is_not_closed_by_the_stream():
    """Injected transports are the caller's to manage; only owned ones close."""
    mcu = MockSTM32()
    stream_frame_to_mcu(gradient_frame(), PANEL_W, PANEL_H, transport=mcu)
    assert mcu.closed is False


def test_receiver_resyncs_past_leading_garbage():
    """A prior aborted frame leaves debris; the magic hunt must skip it."""
    mcu = MockSTM32()
    mcu.write(b"\x00\x01\xaa\x02stale bytes")
    stream_frame_to_mcu(gradient_frame(), PANEL_W, PANEL_H, transport=mcu)
    assert bytes(mcu.pixels) == gradient_frame()


def test_smaller_chunk_size_still_delivers_the_frame():
    payload = gradient_frame()
    mcu = MockSTM32()
    # 480 bytes = exactly one row, the smallest legal chunk for a 240 px panel.
    stats = stream_frame_to_mcu(payload, PANEL_W, PANEL_H, chunk=480, transport=mcu)
    assert bytes(mcu.pixels) == payload
    assert stats["chunks"] == 320   # one per row


# ------------------------------------------------------------------- failures


def test_payload_of_wrong_length_is_refused_before_the_wire():
    mcu = MockSTM32()
    with pytest.raises(DisplayBridgeError, match="needs 153600"):
        stream_frame_to_mcu(gradient_frame()[:-2], PANEL_W, PANEL_H, transport=mcu)
    assert len(mcu.pixels) == 0


def test_little_endian_payload_would_be_wrong_so_big_endian_is_asserted():
    """ST7789 wire order is MSB first: pure red must pack F8 00, not 00 F8."""
    assert rgb_to_rgb565(b"\xff\x00\x00", "big") == b"\xf8\x00"
    assert rgb_to_rgb565(b"\xff\x00\x00", "little") == b"\x00\xf8"


def test_geometry_nak_from_a_rotated_sketch_surfaces_as_an_error():
    """A sketch left on setRotation(1) reports 320x240 and must NAK the header."""
    rotated = MockSTM32(panel_w=320, panel_h=240)
    with pytest.raises(DisplayBridgeError, match="rejected header"):
        stream_frame_to_mcu(gradient_frame(), PANEL_W, PANEL_H, transport=rotated)
    assert rotated.nak_reason == "geometry or protocol"


def test_chunk_not_row_aligned_is_refused_before_the_wire():
    """A mid-row chunk is caught host-side, with the nearest legal size named.

    The receiver would NAK it anyway, but failing here costs no round trip and
    no reflash - and on this board a wasted connection is expensive, since the
    monitor link accepts only one client per boot.
    """
    mcu = MockSTM32()
    with pytest.raises(DisplayBridgeError, match="multiple of 480"):
        stream_frame_to_mcu(gradient_frame(), PANEL_W, PANEL_H, chunk=512, transport=mcu)
    # Nothing reached the MCU: rejected before any write.
    assert mcu.pixels == bytearray()


def test_chunk_larger_than_sketch_buffer_is_naked():
    small = MockSTM32(max_chunk=1024)
    with pytest.raises(DisplayBridgeError, match="rejected header"):
        stream_frame_to_mcu(gradient_frame(), PANEL_W, PANEL_H, chunk=4800, transport=small)


def test_silent_mcu_reports_a_missing_ack_rather_than_hanging():
    class Deaf(MockSTM32):
        def read(self, length=1):
            return b""

    with pytest.raises(DisplayBridgeError, match="did not acknowledge"):
        stream_frame_to_mcu(gradient_frame(), PANEL_W, PANEL_H, transport=Deaf())


def test_unexpected_reply_byte_is_reported_as_desync():
    class Noisy(MockSTM32):
        def read(self, length=1):
            return b"\x99"

    with pytest.raises(DisplayBridgeError, match="unexpected byte 0x99"):
        stream_frame_to_mcu(gradient_frame(), PANEL_W, PANEL_H, transport=Noisy())


def test_corrupted_chunk_is_caught_by_crc_not_drawn():
    """One flipped bit mid-frame must NAK, not paint a torn image."""
    class BitFlipper(MockSTM32):
        def write(self, payload):
            if len(payload) > FRAME_HEADER_BYTES and not self.pixels:
                payload = bytes([payload[0] ^ 0xFF]) + payload[1:]
            super().write(payload)

    flipper = BitFlipper()
    with pytest.raises(DisplayBridgeError, match="rejected chunk"):
        stream_frame_to_mcu(gradient_frame(), PANEL_W, PANEL_H, transport=flipper)
    assert flipper.nak_reason == "chunk crc"


# ------------------------------------------------------------------- CLI


def test_mcu_target_and_options_are_exposed():
    args = build_parser().parse_args([
        "--target", "mcu", "--port", "/dev/ttyACM0",
        "--baud", "921600", "--chunk-bytes", "2048",
    ])
    assert args.target == "mcu"
    assert args.port == "/dev/ttyACM0"
    assert args.baud == 921600
    assert args.chunk_bytes == 2048


def test_mcu_defaults_match_the_sketch_constants():
    args = build_parser().parse_args([])
    # The UNO Q monitor proxy, not a device node: the STM32 has no serial node
    # on this board. Verified on hardware - the sketch ACKs a frame header sent
    # to this endpoint.
    assert args.port == DEFAULT_MCU_PORT == "127.0.0.1:7500"
    assert args.baud == DEFAULT_MCU_BAUD == 115200
    # 8 rows of 240 px. Row-aligned because the receiver takes the SPI bus per
    # chunk; see the deadlock note in frame_receiver.ino.
    assert args.chunk_bytes == DEFAULT_CHUNK_BYTES == 3840
    assert DEFAULT_CHUNK_BYTES % (240 * 2) == 0


# ------------------------------------------------------- transport selection


def test_parse_endpoint_splits_host_and_port():
    assert parse_endpoint("127.0.0.1:7500") == ("127.0.0.1", 7500)
    assert parse_endpoint("localhost:7500") == ("localhost", 7500)


def test_parse_endpoint_rejects_device_paths():
    """A device node must never be read as a hostname."""
    assert parse_endpoint("/dev/ttyGS0") is None
    assert parse_endpoint("/dev/ttyACM0") is None
    # Even a path that contains a colon stays a path.
    assert parse_endpoint("/dev/weird:name") is None


def test_parse_endpoint_rejects_malformed_endpoints():
    assert parse_endpoint("") is None
    assert parse_endpoint("nocolon") is None
    assert parse_endpoint(":7500") is None        # no host
    assert parse_endpoint("host:") is None        # no port
    assert parse_endpoint("host:notaport") is None


def test_tcp_transport_moves_bytes_and_reassembles_split_reads():
    """read(n) must return n bytes even when TCP delivers them in pieces."""
    import socket as _socket
    import threading

    listener = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    listener.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()

    received = []

    def serve():
        conn, _ = listener.accept()
        received.append(conn.recv(5))
        # Deliberately dribble the reply so a single recv() cannot satisfy it.
        conn.sendall(b"AB")
        time.sleep(0.05)
        conn.sendall(b"CD")
        conn.close()

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        with TcpTransport(host=host, port=port, timeout=2.0) as transport:
            transport.write(b"hello")
            assert transport.read(4) == b"ABCD"
    finally:
        thread.join(timeout=3)
        listener.close()

    assert received == [b"hello"]


def test_tcp_transport_read_returns_short_on_timeout():
    """A silent peer yields whatever arrived, not an exception - matching serial."""
    import socket as _socket
    import threading

    listener = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    listener.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()

    held = []

    def serve():
        conn, _ = listener.accept()
        conn.sendall(b"Z")
        held.append(conn)   # keep it open and say nothing more

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        with TcpTransport(host=host, port=port, timeout=0.3) as transport:
            assert transport.read(4) == b"Z"
    finally:
        thread.join(timeout=3)
        for conn in held:
            conn.close()
        listener.close()


def test_tcp_transport_reports_a_dead_listener():
    listener = __import__("socket").socket()
    listener.bind(("127.0.0.1", 0))
    host, port = listener.getsockname()
    listener.close()   # nothing is listening now

    with pytest.raises(TcpTransportError):
        TcpTransport(host=host, port=port, timeout=1.0).open()
