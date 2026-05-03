"""Pipeline orchestration for the edge-side project."""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Optional

from config import (
    DEFAULT_ALERT_CONFIG,
    DEFAULT_CAMERA_CONFIG,
    DEFAULT_MODEL_CONFIG,
    DEFAULT_NETWORK_CONFIG,
)
from modules.alert import DecisionEngine
from modules.inference import Detector
from modules.network import NetworkClient
from modules.vision import CameraCapture
from utils.data_structs import AlertPacket, InferenceResult, VideoFrame


@dataclass
class PipelineStats:
    frames: int = 0
    alerts: int = 0
    errors: int = 0


class EdgePipeline:
    def __init__(
        self,
        camera_config=None,
        model_config=None,
        alert_config=None,
        network_config=None,
        camera: Optional[CameraCapture] = None,
        detector: Optional[Detector] = None,
        alert_engine: Optional[DecisionEngine] = None,
        network: Optional[NetworkClient] = None,
    ) -> None:
        camera_config = camera_config or DEFAULT_CAMERA_CONFIG
        model_config = model_config or DEFAULT_MODEL_CONFIG
        alert_config = alert_config or DEFAULT_ALERT_CONFIG
        network_config = network_config or DEFAULT_NETWORK_CONFIG
        self.camera = camera or CameraCapture(camera_config)
        self.detector = detector or Detector(model_config)
        self.alert_engine = alert_engine or DecisionEngine(
            alert_config, node_id=network_config.node_id
        )
        self.network = network or NetworkClient(network_config)
        self.stats = PipelineStats()
        self.last_frame: VideoFrame | None = None
        self.last_inference: InferenceResult | None = None
        self.last_alert_packet: AlertPacket | None = None
        self._video_stream_running = False
        self._video_thread: threading.Thread | None = None

    def start(self) -> None:
        self.camera.start()
        self.detector.start()
        self.alert_engine.start()
        self.network.start()
        self.start_video_stream()

    def start_video_stream(self) -> None:
        if self._video_stream_running:
            return
        self._video_stream_running = True
        self._video_thread = threading.Thread(target=self._video_stream_loop, name="edge-video-stream", daemon=True)
        self._video_thread.start()

    def _video_stream_loop(self) -> None:
        fps = max(1, int(getattr(self.camera.config, "fps", 10) or 10))
        interval = 1.0 / fps
        while self._video_stream_running:
            started = time.time()
            try:
                frame = self.camera.get_processed_frame()
                self.last_frame = frame
                video_data = self.network.encode_video_frame(frame)
                self.network.send_video(video_data)
            except Exception:
                self.stats.errors += 1
            elapsed = time.time() - started
            time.sleep(max(0.001, interval - elapsed))

    def step(self) -> None:
        frame = self.camera.get_processed_frame()
        self.last_frame = frame
        inference = self.detector.infer(frame)
        self.last_inference = inference
        alert_triggered = self.alert_engine.process_result(inference)

        if alert_triggered:
            alert_packet = self.alert_engine.generate_alert_packet(frame)
            self.last_alert_packet = alert_packet
            self.network.send_alert(alert_packet)
            self.stats.alerts += 1
        else:
            self.last_alert_packet = None

        remote_command = self.network.recv_remote_command()
        if remote_command:
            self._apply_remote_command(remote_command)

        self.stats.frames += 1

    def _apply_remote_command(self, command) -> None:
        if not isinstance(command, dict):
            return

        target = command.get("target")
        if command.get("command") == "update_config":
            config = command.get("config", {})
            if not isinstance(config, dict):
                return
            if "confidence_threshold" in config:
                self.detector.update_conf_threshold(float(config["confidence_threshold"]))
            if "alert_cooldown_seconds" in config or "cooldown_seconds" in config:
                cooldown = config.get("alert_cooldown_seconds", config.get("cooldown_seconds"))
                self.alert_engine.config.cooldown_seconds = int(cooldown)
            if "alert_conf_threshold" in config:
                self.alert_engine.config.alert_conf_threshold = float(config["alert_conf_threshold"])
            return

        if target == "inference" and "conf_threshold" in command:
            self.detector.update_conf_threshold(float(command["conf_threshold"]))
        elif target == "alert" and "config" in command:
            config = command["config"]
            alert_methods = config.get("alert_methods", self.alert_engine.config.alert_methods)
            if alert_methods is None:
                alert_methods = self.alert_engine.config.alert_methods
            self.alert_engine.update_alert_config(
                self.alert_engine.config.__class__(
                    alert_conf_threshold=float(config.get("alert_conf_threshold", self.alert_engine.config.alert_conf_threshold)),
                    consecutive_frames=int(config.get("consecutive_frames", self.alert_engine.config.consecutive_frames)),
                    cooldown_seconds=int(config.get("cooldown_seconds", self.alert_engine.config.cooldown_seconds)),
                    alert_methods=list(alert_methods),
                    trigger_classes=list(config.get("trigger_classes", self.alert_engine.config.trigger_classes)),
                    person_class_names=list(config.get("person_class_names", self.alert_engine.config.person_class_names)),
                    helmet_class_names=list(config.get("helmet_class_names", self.alert_engine.config.helmet_class_names)),
                    helmet_missing_class_names=list(config.get("helmet_missing_class_names", self.alert_engine.config.helmet_missing_class_names)),
                    helmet_match_iou_threshold=float(config.get("helmet_match_iou_threshold", self.alert_engine.config.helmet_match_iou_threshold)),
                    helmet_head_region_ratio=float(config.get("helmet_head_region_ratio", self.alert_engine.config.helmet_head_region_ratio)),
                    fall_aspect_ratio_threshold=float(config.get("fall_aspect_ratio_threshold", self.alert_engine.config.fall_aspect_ratio_threshold)),
                    fall_min_confidence=float(config.get("fall_min_confidence", self.alert_engine.config.fall_min_confidence)),
                    smoke_class_names=list(config.get("smoke_class_names", self.alert_engine.config.smoke_class_names)),
                    smoke_alarm_enabled=bool(config.get("smoke_alarm_enabled", self.alert_engine.config.smoke_alarm_enabled)),
                    smoke_alarm_classes=list(config.get("smoke_alarm_classes", self.alert_engine.config.smoke_alarm_classes)),
                    smoke_alarm_window_frames=int(config.get("smoke_alarm_window_frames", self.alert_engine.config.smoke_alarm_window_frames)),
                    smoke_alarm_min_hits=int(config.get("smoke_alarm_min_hits", self.alert_engine.config.smoke_alarm_min_hits)),
                    smoke_alarm_avg_confidence=float(config.get("smoke_alarm_avg_confidence", self.alert_engine.config.smoke_alarm_avg_confidence)),
                    smoke_alarm_type=str(config.get("smoke_alarm_type", self.alert_engine.config.smoke_alarm_type)),
                    smoke_sensor_baseline_ppm=float(config.get("smoke_sensor_baseline_ppm", self.alert_engine.config.smoke_sensor_baseline_ppm)),
                    smoke_sensor_alarm_ppm=float(config.get("smoke_sensor_alarm_ppm", self.alert_engine.config.smoke_sensor_alarm_ppm)),
                    smoke_sensor_max_ppm=float(config.get("smoke_sensor_max_ppm", self.alert_engine.config.smoke_sensor_max_ppm)),
                    smoke_sensor_weight=float(config.get("smoke_sensor_weight", self.alert_engine.config.smoke_sensor_weight)),
                )
            )

    def run(self, iterations: Optional[int] = None, interval: float = 0.2) -> PipelineStats:
        self.start()
        count = 0
        try:
            while iterations is None or count < iterations:
                self.step()
                count += 1
                time.sleep(interval)
        finally:
            self.stop()
        return self.stats

    def stop(self) -> None:
        self._video_stream_running = False
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=2.0)
        self.camera.stop()
        self.detector.stop()
        self.alert_engine.stop()
        self.network.stop()
