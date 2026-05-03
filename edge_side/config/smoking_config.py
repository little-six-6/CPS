"""Smoking detection node configuration."""

from config.node_config_factory import make_alert_config, make_model_config, make_network_config, make_shared_camera_config


CAMERA_CONFIG = make_shared_camera_config(camera_id=0)
MODEL_CONFIG = make_model_config("smoking", threshold=0.06, classes=["person", "cigarette", "smoking", "smoke"])
ALERT_CONFIG = make_alert_config(["cigarette", "smoking", "smoke"], confidence=0.40, consecutive_frames=1, cooldown_seconds=5)
NETWORK_CONFIG = make_network_config("smoking-001", "smoking", udp_port=5002, tcp_port=5003)
