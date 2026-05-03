"""Protocol helpers for network transfer."""

from __future__ import annotations

import base64
import json
import struct
import time
import zlib
from dataclasses import asdict
from enum import IntEnum
from typing import Any

from utils.data_structs import AlertPacket, VideoFrame, VideoFrameBytes

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None


FRAME_HEADER = b"\xAA\x55"
NODE_ID_SIZE = 16


class MessageType(IntEnum):
    REGISTER = 0x01
    HEARTBEAT = 0x02
    ALERT = 0x03
    VIDEO = 0x04
    INFERENCE = 0x05
    CONTROL = 0x06


def _node_id_bytes(node_id: str) -> bytes:
    return node_id.encode("utf-8")[:NODE_ID_SIZE].ljust(NODE_ID_SIZE, b"\x00")


def encode_frame(msg_type: MessageType | int, node_id: str, payload: bytes | dict[str, Any] | None = None) -> bytes:
    if payload is None:
        payload_bytes = b""
    elif isinstance(payload, bytes):
        payload_bytes = payload
    else:
        payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = FRAME_HEADER + bytes([int(msg_type)]) + _node_id_bytes(node_id) + struct.pack("!I", len(payload_bytes))
    crc = zlib.crc32(header[2:] + payload_bytes) & 0xFFFFFFFF
    return header + payload_bytes + struct.pack("!I", crc)


def encode_video_frame(frame: VideoFrame) -> VideoFrameBytes:
    if cv2 is not None and np is not None and hasattr(frame.raw_frame, "shape"):
        frame_image = frame.raw_frame
        for quality in (70, 55, 40, 30):
            ok, encoded = cv2.imencode(".jpg", frame_image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if ok and len(encoded) <= 60000:
                return VideoFrameBytes(
                    frame_id=frame.frame_id,
                    timestamp=frame.timestamp,
                    frame_bytes=encoded.tobytes(),
                )

        try:
            resized = cv2.resize(frame.raw_frame, (480, 360))
            ok, encoded = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 45])
            if ok:
                return VideoFrameBytes(
                    frame_id=frame.frame_id,
                    timestamp=frame.timestamp,
                    frame_bytes=encoded.tobytes(),
                )
        except Exception:
            pass

    payload = json.dumps(
        {
            "frame_id": frame.frame_id,
            "timestamp": frame.timestamp,
            "width": frame.width,
            "height": frame.height,
        }
    ).encode("utf-8")
    return VideoFrameBytes(frame_id=frame.frame_id, timestamp=frame.timestamp, frame_bytes=payload)


def encode_alert_packet(alert: AlertPacket) -> bytes:
    payload = asdict(alert)
    payload["frame_snapshot"] = base64.b64encode(alert.frame_snapshot).decode("ascii")
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def encode_alert_frame(alert: AlertPacket) -> bytes:
    return encode_frame(MessageType.ALERT, alert.node_id, encode_alert_packet(alert))


def encode_video_frame_packet(node_id: str, data: VideoFrameBytes) -> bytes:
    return encode_frame(MessageType.VIDEO, node_id, data.frame_bytes)


def encode_register_packet(node_id: str, node_type: str) -> bytes:
    return encode_frame(MessageType.REGISTER, node_id, {"node_type": node_type})


def encode_heartbeat_packet(node_id: str, node_type: str) -> bytes:
    return encode_frame(MessageType.HEARTBEAT, node_id, {"node_type": node_type, "timestamp": time.time()})


def decode_remote_command(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None
