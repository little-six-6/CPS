"""Module 2: edge inference."""

from __future__ import annotations

import time
from typing import Optional

from core.base_module import BaseModule
from modules.inference.model_loader import ModelLoader
from utils.data_structs import InferenceResult, ModelConfig, VideoFrame


class Detector(BaseModule):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__("inference")
        self.config = config
        self.loader = ModelLoader(config)
        self.threshold = config.conf_threshold

    def start(self) -> bool:
        self.state.running = self.loader.load()
        self.state.initialized = True
        return self.state.running

    def load_model(self) -> bool:
        return self.loader.load()

    def infer(self, frame: VideoFrame) -> InferenceResult:
        if not self.loader.loaded:
            self.loader.load()
        targets = self.loader.predict(frame)
        active_aliases = set(self.config.active_model_aliases or [])
        if active_aliases:
            filtered = [target for target in targets if target.source_model in active_aliases or target.source_model == "fallback"]
        else:
            filtered = targets
        neutral = set(getattr(self.config, "neutral_class_names", []) or [])
        if neutral:
            has_abnormal = any(target.class_name not in neutral for target in filtered)
        else:
            has_abnormal = len(filtered) > 0
        return InferenceResult(
            frame_id=frame.frame_id,
            timestamp=time.time(),
            targets=filtered,
            has_abnormal=has_abnormal,
        )

    def update_conf_threshold(self, thres: float) -> None:
        self.threshold = thres
        self.config.conf_threshold = thres

    def unload_model(self) -> None:
        self.loader.unload()

    def stop(self) -> None:
        self.unload_model()
        self.state.running = False
