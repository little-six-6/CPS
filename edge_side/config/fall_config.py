"""Fall detection node configuration."""

from config.node_config_factory import make_alert_config, make_model_config, make_network_config, make_shared_camera_config


CAMERA_CONFIG = make_shared_camera_config(camera_id=0)
MODEL_CONFIG = make_model_config("ppe", threshold=0.10, classes=["person", "fall"])
ALERT_CONFIG = make_alert_config(["fall"], confidence=0.55, consecutive_frames=2, cooldown_seconds=5)
NETWORK_CONFIG = make_network_config("fall-001", "fall", udp_port=5006, tcp_port=5007)

