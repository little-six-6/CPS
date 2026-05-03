"""Shared helpers for single-detection node configurations."""

from __future__ import annotations

from pathlib import Path

from utils.data_structs import AlertConfig, CameraConfig, ModelConfig, NetworkConfig


EDGE_SIDE_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SHARED_DIR = EDGE_SIDE_ROOT / "runtime" / "shared_camera"

MODEL_PATHS = {
    "fire_smoke": "models/yolov26-fire-detection.pt",
    "smoking": "models/Smoking-detection-YOLO26s.pt",
    "ppe": "models/vyra-yolo-ppe-detection.pt",
}


LABEL_ALIAS_MAP = {
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


def make_shared_camera_config(camera_id: int = 0) -> CameraConfig:
    return CameraConfig(
        camera_id=camera_id,
        resolution=(640, 480),
        fps=10,
        model_input_size=(640, 640),
        shared_mode=True,
        shared_frame_path=str(RUNTIME_SHARED_DIR / "latest.jpg"),
        shared_lock_path=str(RUNTIME_SHARED_DIR / "camera_owner.lock"),
        shared_stale_seconds=3.0,
    )


def make_model_config(alias: str, threshold: float, classes: list[str]) -> ModelConfig:
    return ModelConfig(
        model_path=MODEL_PATHS.get(alias, "models/yolo11n.pt"),
        conf_threshold=threshold,
        class_names=classes,
        device="cpu",
        local_model_paths={alias: MODEL_PATHS[alias]},
        model_conf_thresholds={alias: threshold},
        label_alias_map={alias: LABEL_ALIAS_MAP.get(alias, {})},
        active_model_aliases=[alias],
        neutral_class_names=["person", "helmet"],
    )


def make_network_config(node_id: str, node_type: str, udp_port: int, tcp_port: int) -> NetworkConfig:
    return NetworkConfig(
        server_ip="127.0.0.1",
        udp_video_port=udp_port,
        tcp_alert_port=tcp_port,
        node_id=node_id,
        node_type=node_type,
        heartbeat_interval_seconds=5.0,
        use_framed_protocol=True,
    )


def make_alert_config(
    trigger_classes: list[str],
    confidence: float = 0.6,
    consecutive_frames: int = 2,
    cooldown_seconds: int = 5,
    smoke_alarm_enabled: bool = False,
    smoke_alarm_window_frames: int = 5,
    smoke_alarm_min_hits: int = 2,
    smoke_alarm_avg_confidence: float = 0.45,
) -> AlertConfig:
    return AlertConfig(
        alert_conf_threshold=confidence,
        consecutive_frames=consecutive_frames,
        cooldown_seconds=cooldown_seconds,
        alert_methods=["console"],
        trigger_classes=trigger_classes,
        person_class_names=["person"],
        helmet_class_names=["helmet", "hardhat", "safety_helmet"],
        helmet_missing_class_names=["no_hardhat"],
        helmet_match_iou_threshold=0.15,
        helmet_head_region_ratio=0.45,
        fall_aspect_ratio_threshold=1.3,
        fall_min_confidence=0.5,
        smoke_alarm_enabled=smoke_alarm_enabled,
        smoke_alarm_classes=["smoke"],
        smoke_alarm_window_frames=smoke_alarm_window_frames,
        smoke_alarm_min_hits=smoke_alarm_min_hits,
        smoke_alarm_avg_confidence=smoke_alarm_avg_confidence,
        smoke_alarm_type="smoke_alarm",
    )
