"""Module 4: local decision and alerting."""

from __future__ import annotations

import time
import uuid
from typing import List, Optional, Tuple

from core.base_module import BaseModule
from modules.alert.local_alert import LocalAlert
from modules.alert.smoke_alarm import SmokeAlarmEvent, SmokeAlarmSimulator
from utils.data_structs import AlertConfig, AlertPacket, InferenceResult, VideoFrame


class DecisionEngine(BaseModule):
    def __init__(self, config: AlertConfig, node_id: str = "edge-001") -> None:
        super().__init__("alert")
        self.config = config
        self.node_id = node_id
        self.alert = LocalAlert(config.alert_methods)
        self._consecutive_abnormal = 0
        self._last_alert_ts = 0.0
        self._last_result: Optional[InferenceResult] = None
        self._last_triggered_events: List[Tuple[str, str, float, list[float]]] = []
        self.smoke_alarm = SmokeAlarmSimulator(config)

    def start(self) -> bool:
        self.state.running = True
        self.state.initialized = True
        return True

    def process_result(self, res: InferenceResult) -> bool:
        self._last_result = res
        self._last_triggered_events = self._extract_events(res)
        smoke_alarm_event = self.smoke_alarm.evaluate(res)
        if smoke_alarm_event is not None:
            self._last_triggered_events.append(self._event_tuple(smoke_alarm_event))
        if self._last_triggered_events:
            self._consecutive_abnormal += 1
        else:
            self._consecutive_abnormal = 0

        should_alert = (
            self._consecutive_abnormal >= self.config.consecutive_frames
            and (time.time() - self._last_alert_ts) >= self.config.cooldown_seconds
        )
        if should_alert:
            self.trigger_local_alert()
            self._last_alert_ts = time.time()
            self._consecutive_abnormal = 0
        return should_alert

    def trigger_local_alert(self) -> None:
        if not self._last_triggered_events:
            self.alert.trigger("abnormal condition detected")
            return
        event_text = ", ".join(event_type for event_type, _, _, _ in self._last_triggered_events)
        frame_id = self._last_result.frame_id if self._last_result else -1
        self.alert.trigger(f"{event_text} detected at frame {frame_id}")

    def generate_alert_packet(self, frame: VideoFrame) -> AlertPacket:
        result = self._last_result
        alert_type = "abnormal_event"
        confidence = 0.0
        bbox = [0.0, 0.0, 0.0, 0.0]
        description = "abnormal event detected"

        if self._last_triggered_events:
            top_event = max(self._last_triggered_events, key=lambda item: item[2])
            alert_type = top_event[0]
            confidence = top_event[2]
            bbox = top_event[3]
            description = top_event[1]
        elif result and result.targets:
            top_target = result.targets[0]
            alert_type = top_target.class_name
            confidence = top_target.confidence
            bbox = top_target.bbox
            description = f"Detected {top_target.class_name} with confidence {top_target.confidence:.2f}"

        frame_snapshot = self._serialize_snapshot(frame)
        level = "high" if confidence >= 0.8 else "medium" if confidence >= 0.6 else "low"
        return AlertPacket(
            alert_id=str(uuid.uuid4()),
            node_id=self.node_id,
            timestamp=time.time(),
            alert_type=alert_type,
            alert_level=level,
            confidence=confidence,
            bbox=bbox,
            frame_snapshot=frame_snapshot,
            description=description,
        )

    def _serialize_snapshot(self, frame: VideoFrame) -> bytes:
        raw = frame.raw_frame
        if isinstance(raw, bytes):
            return raw
        try:
            import cv2

            ok, encoded = cv2.imencode(".jpg", raw)
            if ok:
                return encoded.tobytes()
        except Exception:
            pass
        try:
            import json

            return json.dumps(
                {
                    "frame_id": frame.frame_id,
                    "timestamp": frame.timestamp,
                    "width": frame.width,
                    "height": frame.height,
                }
            ).encode("utf-8")
        except Exception:
            return repr(raw).encode("utf-8")

    def update_alert_config(self, config: AlertConfig) -> None:
        self.config = config
        self.alert = LocalAlert(config.alert_methods)
        self.smoke_alarm.update_config(config)

    def _event_tuple(self, event: SmokeAlarmEvent) -> Tuple[str, str, float, list[float]]:
        return (event.alert_type, event.description, event.confidence, event.bbox)

    def _extract_events(self, res: InferenceResult) -> List[Tuple[str, str, float, list[float]]]:
        events: List[Tuple[str, str, float, list[float]]] = []
        trigger_classes = {self._normalize_label(value) for value in (self.config.trigger_classes or [])}
        smoke_classes = {
            self._normalize_label(value)
            for value in [
                *(getattr(self.config, "smoke_class_names", []) or []),
                *(getattr(self.config, "smoke_alarm_classes", []) or []),
            ]
        }
        person_classes = {self._normalize_label(value) for value in (self.config.person_class_names or [])}
        helmet_missing_classes = {
            self._normalize_label(value) for value in (getattr(self.config, "helmet_missing_class_names", []) or [])
        }
        helmet_classes = {self._normalize_label(value) for value in (self.config.helmet_class_names or [])}
        ppe_people = [target for target in res.targets if target.source_model == "ppe" and self._normalize_label(target.class_name) in person_classes]
        ppe_helmets = [
            target
            for target in res.targets
            if target.source_model == "ppe" and self._normalize_label(target.class_name) in helmet_classes
        ]

        for target in res.targets:
            class_name = self._normalize_label(target.class_name)
            if class_name in smoke_classes:
                continue

            if class_name in trigger_classes:
                if target.confidence < self.config.alert_conf_threshold:
                    continue
                events.append(
                    (
                        class_name,
                        f"Detected {target.class_name} with confidence {target.confidence:.2f}",
                        target.confidence,
                        target.bbox,
                    )
                )
                continue

            if class_name in person_classes and self._looks_like_fall(target):
                events.append(
                    (
                        "fall",
                        f"Possible fall detected with confidence {target.confidence:.2f}",
                        target.confidence,
                        target.bbox,
                    )
                )

            if class_name in helmet_missing_classes:
                events.append(
                    (
                        "no_hardhat",
                        f"Detected {target.class_name} with confidence {target.confidence:.2f}",
                        target.confidence,
                        target.bbox,
                    )
                )

        if ppe_people and not self._has_helmet_match(ppe_people, ppe_helmets):
            for person in ppe_people:
                events.append(
                    (
                        "no_hardhat",
                        f"Person without helmet detected with confidence {person.confidence:.2f}",
                        person.confidence,
                        person.bbox,
                    )
                )

        return events

    def _looks_like_fall(self, target) -> bool:
        try:
            x1, y1, x2, y2 = target.bbox
            width = max(0.0, float(x2) - float(x1))
            height = max(0.0, float(y2) - float(y1))
            if height <= 0:
                return False
            aspect_ratio = width / height
            return target.confidence >= self.config.fall_min_confidence and aspect_ratio >= self.config.fall_aspect_ratio_threshold
        except Exception:
            return False

    def _normalize_label(self, label: str) -> str:
        return label.strip().lower().replace(" ", "_").replace("-", "_")

    def _has_helmet_match(self, people, helmets) -> bool:
        for person in people:
            for helmet in helmets:
                if self._helmet_on_head(person.bbox, helmet.bbox):
                    return True
        return False

    def _helmet_on_head(self, person_bbox, helmet_bbox) -> bool:
        try:
            px1, py1, px2, py2 = [float(v) for v in person_bbox]
            hx1, hy1, hx2, hy2 = [float(v) for v in helmet_bbox]
            person_width = max(0.0, px2 - px1)
            person_height = max(0.0, py2 - py1)
            if person_width <= 0 or person_height <= 0:
                return False

            head_bottom = py1 + person_height * self.config.helmet_head_region_ratio
            helmet_cx = (hx1 + hx2) / 2.0
            helmet_cy = (hy1 + hy2) / 2.0

            in_horizontal = px1 <= helmet_cx <= px2
            in_head_zone = py1 <= helmet_cy <= head_bottom
            return in_horizontal and in_head_zone and self._bbox_iou(person_bbox, helmet_bbox) >= min(
                self.config.helmet_match_iou_threshold, 0.05
            )
        except Exception:
            return False

    def _bbox_iou(self, a, b) -> float:
        try:
            ax1, ay1, ax2, ay2 = [float(v) for v in a]
            bx1, by1, bx2, by2 = [float(v) for v in b]
            inter_x1 = max(ax1, bx1)
            inter_y1 = max(ay1, by1)
            inter_x2 = min(ax2, bx2)
            inter_y2 = min(ay2, by2)
            inter_w = max(0.0, inter_x2 - inter_x1)
            inter_h = max(0.0, inter_y2 - inter_y1)
            inter_area = inter_w * inter_h
            a_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
            b_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
            denom = a_area + b_area - inter_area
            if denom <= 0:
                return 0.0
            return inter_area / denom
        except Exception:
            return 0.0

    def stop(self) -> None:
        self.state.running = False
