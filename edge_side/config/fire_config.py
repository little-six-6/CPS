"""Fire and smoke detection node configuration."""

from config.node_config_factory import make_alert_config, make_model_config, make_network_config, make_shared_camera_config


CAMERA_CONFIG = make_shared_camera_config(camera_id=0)
MODEL_CONFIG = make_model_config("fire_smoke", threshold=0.15, classes=["fire", "smoke"])
ALERT_CONFIG = make_alert_config(
    ["fire"],
    confidence=0.35,
    consecutive_frames=2,
    cooldown_seconds=3,
)
ALERT_CONFIG.smoke_alarm_enabled = True
ALERT_CONFIG.smoke_alarm_classes = ["smoke"]
ALERT_CONFIG.smoke_alarm_window_frames = 5
ALERT_CONFIG.smoke_alarm_min_hits = 2
ALERT_CONFIG.smoke_alarm_avg_confidence = 0.30
ALERT_CONFIG.smoke_sensor_baseline_ppm = 80.0
ALERT_CONFIG.smoke_sensor_alarm_ppm = 300.0
ALERT_CONFIG.smoke_sensor_max_ppm = 1000.0
ALERT_CONFIG.smoke_sensor_weight = 0.35
NETWORK_CONFIG = make_network_config("fire-smoke-001", "fire_smoke", udp_port=5000, tcp_port=5001)
