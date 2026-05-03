"""Network configuration defaults."""

from utils.data_structs import NetworkConfig


DEFAULT_NETWORK_CONFIG = NetworkConfig(
    server_ip="127.0.0.1",
    udp_video_port=5000,
    tcp_alert_port=5001,
    node_id="edge-001",
)
