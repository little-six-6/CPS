"""Application-layer protocol encoder and parser.

Frame format:
    | header(2B) | type(1B) | node_id(16B) | length(4B) | data | crc32(4B) |
"""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Iterable, Tuple


FRAME_HEADER = b"\xAA\x55"
NODE_ID_SIZE = 16
LENGTH_SIZE = 4
CRC_SIZE = 4
FIXED_HEADER_SIZE = len(FRAME_HEADER) + 1 + NODE_ID_SIZE + LENGTH_SIZE
MIN_FRAME_SIZE = FIXED_HEADER_SIZE + CRC_SIZE


class MessageType(IntEnum):
    REGISTER = 0x01
    HEARTBEAT = 0x02
    ALERT = 0x03
    VIDEO = 0x04
    INFERENCE = 0x05
    CONTROL = 0x06


@dataclass(frozen=True)
class ProtocolFrame:
    msg_type: MessageType
    node_id: str
    payload: bytes

    def json(self) -> dict[str, Any]:
        if not self.payload:
            return {}
        return json.loads(self.payload.decode("utf-8"))


class ProtocolError(ValueError):
    """Raised when a protocol frame is invalid."""


def normalize_node_id(node_id: str) -> bytes:
    raw = node_id.encode("utf-8")[:NODE_ID_SIZE]
    return raw.ljust(NODE_ID_SIZE, b"\x00")


def decode_node_id(raw: bytes) -> str:
    return raw.rstrip(b"\x00").decode("utf-8", errors="replace")


def encode_frame(msg_type: MessageType | int, node_id: str, payload: bytes | dict[str, Any] | None = None) -> bytes:
    if payload is None:
        payload_bytes = b""
    elif isinstance(payload, bytes):
        payload_bytes = payload
    else:
        payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    msg_type_value = int(msg_type)
    header = FRAME_HEADER + bytes([msg_type_value]) + normalize_node_id(node_id) + struct.pack("!I", len(payload_bytes))
    crc = zlib.crc32(header[2:] + payload_bytes) & 0xFFFFFFFF
    return header + payload_bytes + struct.pack("!I", crc)


def parse_frame(raw: bytes) -> ProtocolFrame:
    if len(raw) < MIN_FRAME_SIZE:
        raise ProtocolError("frame is too short")
    if raw[:2] != FRAME_HEADER:
        raise ProtocolError("invalid frame header")

    msg_type_value = raw[2]
    try:
        msg_type = MessageType(msg_type_value)
    except ValueError as exc:
        raise ProtocolError(f"unknown message type: 0x{msg_type_value:02x}") from exc

    node_id = decode_node_id(raw[3 : 3 + NODE_ID_SIZE])
    payload_len = struct.unpack("!I", raw[3 + NODE_ID_SIZE : FIXED_HEADER_SIZE])[0]
    expected_size = FIXED_HEADER_SIZE + payload_len + CRC_SIZE
    if len(raw) != expected_size:
        raise ProtocolError(f"frame size mismatch: expected {expected_size}, got {len(raw)}")

    payload = raw[FIXED_HEADER_SIZE : FIXED_HEADER_SIZE + payload_len]
    expected_crc = struct.unpack("!I", raw[-CRC_SIZE:])[0]
    actual_crc = zlib.crc32(raw[2:FIXED_HEADER_SIZE] + payload) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise ProtocolError("crc32 check failed")

    return ProtocolFrame(msg_type=msg_type, node_id=node_id, payload=payload)


class StreamFrameParser:
    """Incrementally parses protocol frames from a TCP byte stream."""

    def __init__(self, max_payload_size: int = 8 * 1024 * 1024) -> None:
        self._buffer = bytearray()
        self._max_payload_size = max_payload_size

    def feed(self, chunk: bytes) -> list[ProtocolFrame]:
        self._buffer.extend(chunk)
        frames: list[ProtocolFrame] = []

        while True:
            header_index = self._buffer.find(FRAME_HEADER)
            if header_index < 0:
                if len(self._buffer) > 1:
                    del self._buffer[:-1]
                break
            if header_index:
                del self._buffer[:header_index]
            if len(self._buffer) < MIN_FRAME_SIZE:
                break

            payload_len = struct.unpack("!I", self._buffer[3 + NODE_ID_SIZE : FIXED_HEADER_SIZE])[0]
            if payload_len > self._max_payload_size:
                del self._buffer[:2]
                raise ProtocolError(f"payload too large: {payload_len}")

            frame_size = FIXED_HEADER_SIZE + payload_len + CRC_SIZE
            if len(self._buffer) < frame_size:
                break

            raw_frame = bytes(self._buffer[:frame_size])
            del self._buffer[:frame_size]
            frames.append(parse_frame(raw_frame))

        return frames


def looks_like_protocol(raw: bytes) -> bool:
    return raw.startswith(FRAME_HEADER)


def decode_json_payload(payload: bytes) -> dict[str, Any]:
    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


def iter_udp_frames(datagram: bytes) -> Iterable[Tuple[ProtocolFrame | None, bytes]]:
    """Yield parsed UDP frame or raw payload for legacy datagrams."""
    if looks_like_protocol(datagram):
        yield parse_frame(datagram), b""
    else:
        yield None, datagram

