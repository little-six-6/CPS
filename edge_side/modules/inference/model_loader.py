"""Local multi-model loader used by the inference module."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ultralytics import YOLO  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    YOLO = None

from utils.data_structs import DetectionTarget, ModelConfig, VideoFrame


def _normalize_label(label: str) -> str:
    return label.strip().lower().replace(" ", "_").replace("-", "_")


def _map_label(alias: str, raw_label: str, config: ModelConfig) -> str:
    normalized = _normalize_label(raw_label)
    alias_map = config.label_alias_map.get(alias, {})
    if normalized in alias_map:
        return alias_map[normalized]
    return normalized


class ModelLoader:
    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self.loaded = False
        self._models: Dict[str, Any] = {}
        self._resolved_paths: Dict[str, str] = {}
        self.last_backend: str = "uninitialized"
        self.last_model_id: Optional[str] = None
        self.last_prediction_count: int = 0
        self.last_error: Optional[str] = None

    def load(self) -> bool:
        self.loaded = True

        if YOLO is None:
            self._models = {}
            self.last_backend = "fallback"
            self.last_error = "ultralytics package is not installed"
            return True

        self._models = {}
        self._resolved_paths = {}
        load_errors: List[str] = []

        active_aliases = set(self.config.active_model_aliases or self.config.local_model_paths.keys())
        for alias, model_path in self.config.local_model_paths.items():
            if alias not in active_aliases:
                continue
            resolved = self._resolve_model_path(model_path)
            self._resolved_paths[alias] = resolved
            try:
                self._models[alias] = YOLO(resolved)
            except Exception as exc:
                load_errors.append(f"{alias}={resolved}: {exc}")

        if self._models:
            self.last_backend = "local-multi-yolo"
            self.last_model_id = ",".join(self._resolved_paths.values())
            self.last_error = None
        else:
            self.last_backend = "fallback"
            self.last_model_id = None
            self.last_error = "; ".join(load_errors) if load_errors else "failed to load local models"

        return True

    def unload(self) -> None:
        self.loaded = False
        self._models = {}
        self._resolved_paths = {}

    def predict(self, frame: VideoFrame) -> List[DetectionTarget]:
        if not self.loaded:
            self.load()

        local_predictions = self._predict_with_local_models(frame)
        if self.last_backend == "local-multi-yolo":
            return local_predictions

        fallback = self._predict_fallback(frame)
        self.last_backend = "fallback"
        self.last_model_id = self.config.model_path
        self.last_prediction_count = len(fallback)
        self.last_error = self.last_error or "local model unavailable or returned no usable predictions"
        return fallback

    def _resolve_model_path(self, model_path: str) -> str:
        path = Path(model_path)
        if path.is_absolute():
            return str(path)
        return str((Path(__file__).resolve().parents[2] / path).resolve())

    def _predict_with_local_models(self, frame: VideoFrame) -> List[DetectionTarget]:
        if not self._models:
            return []

        parsed: List[DetectionTarget] = []
        for alias, model in self._models.items():
            model_threshold = self.config.model_conf_thresholds.get(alias, self.config.conf_threshold)
            try:
                results = model.predict(
                    source=frame.raw_frame,
                    verbose=False,
                    imgsz=self.config.yolov8_imgsz,
                    conf=model_threshold,
                    device=self.config.device,
                )
            except Exception as exc:
                self.last_error = f"{alias} inference failed: {exc}"
                continue

            if not results:
                continue

            result = results[0]
            names = getattr(result, "names", None) or {}
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue

            try:
                xyxy = boxes.xyxy.cpu().tolist()
                confs = boxes.conf.cpu().tolist()
                clss = boxes.cls.cpu().tolist()
            except Exception:
                continue

            for coords, conf, cls_id in zip(xyxy, confs, clss):
                class_id = int(cls_id)
                raw_name = str(names.get(class_id, f"class_{class_id}"))
                mapped_name = _map_label(alias, raw_name, self.config)
                parsed.append(
                    DetectionTarget(
                        class_id=class_id,
                        class_name=mapped_name,
                        confidence=float(conf),
                        bbox=[float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])],
                        source_model=alias,
                        raw_class_name=raw_name,
                    )
                )

        if parsed:
            self.last_backend = "local-multi-yolo"
            self.last_model_id = ",".join(self._resolved_paths.values())
            self.last_prediction_count = len(parsed)
            self.last_error = None
            return parsed

        self.last_backend = "local-multi-yolo"
        self.last_model_id = ",".join(self._resolved_paths.values())
        self.last_prediction_count = 0
        self.last_error = None
        return []

    def _predict_fallback(self, frame: VideoFrame) -> List[DetectionTarget]:
        self.last_prediction_count = 0
        self.last_error = self.last_error or "fallback backend has no real model output"
        return []
