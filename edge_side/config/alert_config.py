"""Alert configuration defaults."""

from utils.data_structs import AlertConfig


DEFAULT_ALERT_CONFIG = AlertConfig(
    alert_conf_threshold=0.6,
    consecutive_frames=3,
    cooldown_seconds=5,
    alert_methods=["console"],
    trigger_classes=["fire", "smoke", "cigarette", "smoking", "no_hardhat", "fall"],
    person_class_names=["person"],
    helmet_class_names=["helmet", "hardhat", "safety_helmet"],
    helmet_missing_class_names=["no_hardhat"],
    helmet_match_iou_threshold=0.15,
    helmet_head_region_ratio=0.45,
    fall_aspect_ratio_threshold=1.3,
    fall_min_confidence=0.5,
)
