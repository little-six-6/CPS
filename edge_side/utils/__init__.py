"""Utility package."""

from .constants import DEFAULT_INTERVAL_SECONDS, DEFAULT_MAX_ITERATIONS
from .data_structs import (
    AlertConfig,
    AlertPacket,
    CameraConfig,
    DetectionTarget,
    FrameArray,
    InferenceResult,
    ModelConfig,
    NetworkConfig,
    RemoteCommand,
    SendStatus,
    VideoFrame,
    VideoFrameBytes,
)

__all__ = [
    "AlertConfig",
    "AlertPacket",
    "CameraConfig",
    "DetectionTarget",
    "FrameArray",
    "InferenceResult",
    "ModelConfig",
    "NetworkConfig",
    "RemoteCommand",
    "SendStatus",
    "VideoFrame",
    "VideoFrameBytes",
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_MAX_ITERATIONS",
]
