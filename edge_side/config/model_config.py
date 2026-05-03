"""Model configuration defaults."""

from utils.data_structs import ModelConfig


DEFAULT_MODEL_CONFIG = ModelConfig(
    model_path="models/yolo11n.pt",
    conf_threshold=0.5,
    class_names=["normal", "abnormal"],
    device="cpu",
    use_roboflow=False,
    local_model_paths={
        "fire_smoke": "models/yolov26-fire-detection.pt",
        "smoking": "models/Smoking-detection-YOLO26s.pt",
        "ppe": "models/vyra-yolo-ppe-detection.pt",
    },
    model_conf_thresholds={
        "fire_smoke": 0.15,
        "smoking": 0.10,
        "ppe": 0.10,
    },
    label_alias_map={
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
    },
)
