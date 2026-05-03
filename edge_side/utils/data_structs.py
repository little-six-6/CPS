"""Shared data structures for the edge-side project."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = Any  # type: ignore


FrameArray = Any


@dataclass
class CameraConfig:
    camera_id: int = 0
    resolution: Tuple[int, int] = (640, 480)
    fps: int = 15
    model_input_size: Tuple[int, int] = (640, 640)
    shared_mode: bool = False
    shared_frame_path: str = "runtime/shared_camera/latest.jpg"
    shared_lock_path: str = "runtime/shared_camera/camera_owner.lock"
    shared_stale_seconds: float = 3.0


@dataclass
class ModelConfig:
    model_path: str = "models/yolo11n.pt"
    conf_threshold: float = 0.5
    class_names: List[str] = field(default_factory=lambda: ["normal", "abnormal"])
    device: str = "cpu"
    use_roboflow: bool = False
    yolov8_imgsz: int = 640
    neutral_class_names: List[str] = field(default_factory=list)
    local_model_paths: Dict[str, str] = field(
        default_factory=lambda: {
            "fire_smoke": "models/yolov26-fire-detection.pt",
            "smoking": "models/Smoking-detection-YOLO26s.pt",
            "ppe": "models/vyra-yolo-ppe-detection.pt",
        }
    )
    model_conf_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "fire_smoke": 0.15,
            "smoking": 0.10,
            "ppe": 0.10,
        }
    )
    label_alias_map: Dict[str, Dict[str, str]] = field(
        default_factory=lambda: {
            "fire_smoke": {
                "fire": "fire",
                "smoke": "smoke",
            },
            "smoking": {
                "cigarette": "cigarette",
                "smoking": "smoking",
                "smoker": "smoking",
                "person_smoking": "smoking",
                "smoke": "smoke",
                "person": "person",
            },
            "ppe": {
                "hardhat": "helmet",
                "hard_hat": "helmet",
                "hard_hat_helmet": "helmet",
                "helmet": "helmet",
                "no_hardhat": "no_hardhat",
                "no_helmet": "no_hardhat",
                "no_hardhat_detected": "no_hardhat",
                "fall_detected": "fall",
                "fall": "fall",
                "person": "person",
                "worker": "person",
                "human": "person",
            },
        }
    )
    local_model_classes: List[str] = field(
        default_factory=lambda: [
            "person",
            "bicycle",
            "car",
            "motorcycle",
            "airplane",
            "bus",
            "train",
            "truck",
            "boat",
            "traffic light",
        ]
    )
    active_model_aliases: List[str] = field(default_factory=list)


@dataclass
class AlertConfig:
    alert_conf_threshold: float = 0.6
    consecutive_frames: int = 3
    cooldown_seconds: int = 5
    alert_methods: List[str] = field(default_factory=lambda: ["console"])
    trigger_classes: List[str] = field(
        default_factory=lambda: ["fire", "smoke", "cigarette", "smoking", "no_hardhat", "fall"]
    )
    person_class_names: List[str] = field(default_factory=lambda: ["person"])
    helmet_class_names: List[str] = field(default_factory=lambda: ["helmet", "hardhat", "safety_helmet"])
    helmet_missing_class_names: List[str] = field(default_factory=lambda: ["no_hardhat"])
    helmet_match_iou_threshold: float = 0.15
    helmet_head_region_ratio: float = 0.45
    fall_aspect_ratio_threshold: float = 1.3
    fall_min_confidence: float = 0.5
    smoke_class_names: List[str] = field(default_factory=lambda: ["smoke"])
    smoke_sensor_baseline_ppm: float = 80.0
    smoke_sensor_alarm_ppm: float = 300.0
    smoke_sensor_max_ppm: float = 1000.0
    smoke_sensor_weight: float = 0.35
    smoke_alarm_enabled: bool = True
    smoke_alarm_classes: List[str] = field(default_factory=lambda: ["smoke"])
    smoke_alarm_window_frames: int = 5
    smoke_alarm_min_hits: int = 2
    smoke_alarm_avg_confidence: float = 0.30
    smoke_alarm_type: str = "smoke_alarm"


@dataclass
class NetworkConfig:
    server_ip: str = "127.0.0.1"
    udp_video_port: int = 5000
    tcp_alert_port: int = 5001
    node_id: str = "edge-001"
    node_type: str = "unknown"
    heartbeat_interval_seconds: float = 5.0
    use_framed_protocol: bool = True


@dataclass
class VideoFrame:
    frame_id: int
    timestamp: float
    raw_frame: FrameArray
    processed_frame: FrameArray
    width: int
    height: int
    fps: int


@dataclass
class DetectionTarget:
    class_id: int
    class_name: str
    confidence: float
    bbox: List[float]
    source_model: str = ""
    raw_class_name: str = ""


@dataclass
class InferenceResult:
    frame_id: int
    timestamp: float
    targets: List[DetectionTarget]
    has_abnormal: bool


@dataclass
class AlertPacket:
    alert_id: str
    node_id: str
    timestamp: float
    alert_type: str
    alert_level: str
    confidence: float
    bbox: List[float]
    frame_snapshot: bytes
    description: str


@dataclass
class VideoFrameBytes:
    frame_id: int
    timestamp: float
    frame_bytes: bytes


@dataclass
class SendStatus:
    success: bool
    message: str
    timestamp: float


RemoteCommand = Dict[str, Any]
