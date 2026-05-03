"""Configuration for the monitoring center."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
VIDEO_FRAME_DIR = DATA_DIR / "video_frames"
DB_PATH = DATA_DIR / "monitor_center.db"


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    tcp_port: int = 5001
    udp_port: int = 5000
    tcp_ports: tuple[int, ...] = (5001, 5003, 5005, 5007)
    udp_ports: tuple[int, ...] = (5000, 5002, 5004, 5006)
    mjpeg_port: int = 8080
    socket_timeout: float = 1.0
    max_tcp_payload_size: int = 8 * 1024 * 1024
    max_udp_payload_size: int = 65535
    alert_overlay_seconds: float = 10.0


@dataclass(frozen=True)
class NodeConfig:
    offline_timeout_seconds: int = 30
    expected_node_count: int = 4


@dataclass(frozen=True)
class DecisionConfig:
    dedupe_window_seconds: int = 60
    multi_alert_window_seconds: int = 10


DEFAULT_NODE_TYPES = {
    "fire-smoke-001": "fire_smoke",
    "smoking-001": "smoking",
    "helmet-001": "helmet",
    "fall-001": "fall",
}


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_FRAME_DIR.mkdir(parents=True, exist_ok=True)
