"""Configuration package."""

from .alert_config import DEFAULT_ALERT_CONFIG
from .camera_config import DEFAULT_CAMERA_CONFIG
from .model_config import DEFAULT_MODEL_CONFIG
from .network_config import DEFAULT_NETWORK_CONFIG

__all__ = [
    "DEFAULT_ALERT_CONFIG",
    "DEFAULT_CAMERA_CONFIG",
    "DEFAULT_MODEL_CONFIG",
    "DEFAULT_NETWORK_CONFIG",
]
