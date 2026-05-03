"""Smoke alarm simulation based on video detection results."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

from utils.data_structs import AlertConfig, DetectionTarget, InferenceResult


@dataclass
class SmokeAlarmEvent:
    alert_type: str
    description: str
    confidence: float
    bbox: list[float]
    sensor_ppm: float
    sensor_adc: int
    video_confidence: float


class SmokeAlarmSimulator:
    """Converts noisy smoke detections into a stable alarm state."""

    def __init__(self, config: AlertConfig) -> None:
        self.update_config(config)

    def update_config(self, config: AlertConfig) -> None:
        self.config = config
        self._history: deque[float] = deque(maxlen=max(1, int(config.smoke_alarm_window_frames)))

    def evaluate(self, result: InferenceResult) -> SmokeAlarmEvent | None:
        if not self.config.smoke_alarm_enabled:
            return None

        smoke_classes = {self._normalize(label) for label in self.config.smoke_alarm_classes}
        smoke_targets = [
            target
            for target in result.targets
            if self._normalize(target.class_name) in smoke_classes
        ]
        best = max(smoke_targets, key=lambda target: target.confidence, default=None)
        video_confidence = float(best.confidence) if best else 0.0
        self._history.append(video_confidence)

        hits = sum(1 for value in self._history if value > 0.0)
        avg_confidence = sum(self._history) / len(self._history)
        sensor_ppm = self._simulate_sensor_ppm(avg_confidence)
        sensor_adc = self._ppm_to_adc(sensor_ppm)
        sensor_score = self._sensor_score(sensor_ppm)
        fused_confidence = self._fused_confidence(avg_confidence, sensor_score)

        enough_video_hits = hits >= self.config.smoke_alarm_min_hits and avg_confidence >= self.config.smoke_alarm_avg_confidence
        enough_sensor = sensor_ppm >= self.config.smoke_sensor_alarm_ppm
        enough_fused = fused_confidence >= self.config.alert_conf_threshold
        if not (enough_video_hits and enough_sensor and enough_fused):
            return None

        bbox = best.bbox if best else self._fallback_bbox(smoke_targets)
        return SmokeAlarmEvent(
            alert_type=self.config.smoke_alarm_type,
            description=(
                f"Smoke alarm triggered: video={video_confidence:.2f}, avg={avg_confidence:.2f}, "
                f"hits={hits}/{len(self._history)}, simulated_sensor={sensor_ppm:.0f}ppm, "
                f"adc={sensor_adc}, threshold={self.config.smoke_sensor_alarm_ppm:.0f}ppm, "
                f"fused={fused_confidence:.2f}"
            ),
            confidence=fused_confidence,
            bbox=bbox,
            sensor_ppm=sensor_ppm,
            sensor_adc=sensor_adc,
            video_confidence=video_confidence,
        )

    def _simulate_sensor_ppm(self, avg_video_confidence: float) -> float:
        baseline = float(self.config.smoke_sensor_baseline_ppm)
        max_ppm = max(float(self.config.smoke_sensor_alarm_ppm), float(self.config.smoke_sensor_max_ppm))
        confidence = min(1.0, max(0.0, avg_video_confidence))
        return baseline + confidence * (max_ppm - baseline)

    def _ppm_to_adc(self, ppm: float) -> int:
        max_ppm = max(float(self.config.smoke_sensor_alarm_ppm), float(self.config.smoke_sensor_max_ppm))
        return int(round(min(1023.0, max(0.0, ppm / max_ppm * 1023.0))))

    def _sensor_score(self, ppm: float) -> float:
        baseline = float(self.config.smoke_sensor_baseline_ppm)
        alarm_ppm = float(self.config.smoke_sensor_alarm_ppm)
        return min(1.0, max(0.0, (ppm - baseline) / max(1.0, alarm_ppm - baseline)))

    def _fused_confidence(self, avg_video_confidence: float, sensor_score: float) -> float:
        sensor_weight = min(1.0, max(0.0, float(self.config.smoke_sensor_weight)))
        video_score = min(1.0, max(0.0, avg_video_confidence))
        return min(1.0, video_score * (1.0 - sensor_weight) + sensor_score * sensor_weight)

    def _fallback_bbox(self, targets: Iterable[DetectionTarget]) -> list[float]:
        for target in targets:
            return target.bbox
        return [0.0, 0.0, 0.0, 0.0]

    def _normalize(self, label: str) -> str:
        return label.strip().lower().replace(" ", "_").replace("-", "_")
