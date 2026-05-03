"""Safety helmet detection node configuration."""

from config.node_config_factory import make_alert_config, make_model_config, make_network_config, make_shared_camera_config


CAMERA_CONFIG = make_shared_camera_config(camera_id=0)
MODEL_CONFIG = make_model_config("ppe", threshold=0.10, classes=["person", "helmet", "no_hardhat"])
ALERT_CONFIG = make_alert_config(["no_hardhat"], confidence=0.55, consecutive_frames=2, cooldown_seconds=5)
NETWORK_CONFIG = make_network_config("helmet-001", "helmet", udp_port=5004, tcp_port=5005)

