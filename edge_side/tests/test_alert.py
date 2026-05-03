import time

from modules.alert import DecisionEngine
from utils.data_structs import AlertConfig, DetectionTarget, InferenceResult


def _result(frame_id, confidence):
    targets = []
    if confidence:
        targets.append(
            DetectionTarget(
                class_id=0,
                class_name="smoke",
                confidence=confidence,
                bbox=[10, 20, 120, 180],
                source_model="fire_smoke",
            )
        )
    return InferenceResult(frame_id=frame_id, timestamp=time.time(), targets=targets, has_abnormal=bool(targets))


def test_smoke_alarm_requires_persistent_smoke():
    config = AlertConfig(
        alert_conf_threshold=0.3,
        consecutive_frames=1,
        cooldown_seconds=0,
        trigger_classes=["fire"],
        smoke_alarm_enabled=True,
        smoke_alarm_window_frames=3,
        smoke_alarm_min_hits=2,
        smoke_alarm_avg_confidence=0.35,
    )
    engine = DecisionEngine(config, node_id="fire-smoke-001")

    assert engine.process_result(_result(1, 0.8)) is False
    assert engine.process_result(_result(2, 0.0)) is False
    assert engine.process_result(_result(3, 0.8)) is True

    packet = engine.generate_alert_packet(
        type(
            "Frame",
            (),
            {
                "frame_id": 3,
                "timestamp": time.time(),
                "raw_frame": b"frame",
                "width": 640,
                "height": 480,
            },
        )()
    )
    assert packet.alert_type == "smoke_alarm"
    assert packet.confidence >= 0.5
