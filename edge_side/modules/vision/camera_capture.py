"""Module 1: video capture and preprocessing."""

from __future__ import annotations

import time
import threading
from pathlib import Path
from typing import Optional

from core.base_module import BaseModule
from utils.data_structs import CameraConfig, VideoFrame

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None


class CameraCapture(BaseModule):
    def __init__(self, config: CameraConfig) -> None:
        super().__init__("vision")
        self.config = config
        self._capture = None
        self._frame_id = 0
        self._dummy_mode = False
        self._shared_owner = False
        self._lock = threading.RLock()

    def start(self) -> bool:
        if self.state.running:
            return True

        if cv2 is None:
            self._dummy_mode = True
            self.state.running = True
            self.state.initialized = True
            return True

        if self.config.shared_mode:
            self._shared_owner = self._claim_shared_camera()
            if not self._shared_owner:
                self.state.running = True
                self.state.initialized = True
                return True

        self._capture = cv2.VideoCapture(self.config.camera_id)
        if self._capture is not None:
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.resolution[0])
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.resolution[1])
            self._capture.set(cv2.CAP_PROP_FPS, self.config.fps)
        if self._capture is None or not self._capture.isOpened():
            self._dummy_mode = True
            if self._capture is not None:
                self._capture.release()
                self._capture = None
            if self._shared_owner:
                self._release_shared_camera()
                self._shared_owner = False
        self.state.running = True
        self.state.initialized = True
        return True

    def _build_dummy_frame(self):
        width, height = self.config.resolution
        if np is not None:
            return np.zeros((height, width, 3), dtype=np.uint8)
        return bytes(f"dummy-frame-{self._frame_id}", encoding="utf-8")

    def _preprocess(self, frame):
        if cv2 is None or np is None:
            return frame
        target_width, target_height = self.config.model_input_size
        resized = cv2.resize(frame, (target_width, target_height))
        return resized

    def get_processed_frame(self) -> VideoFrame:
        with self._lock:
            if not self.state.running:
                self.start()

            self._frame_id += 1
            timestamp = time.time()
            width, height = self.config.resolution

            if self.config.shared_mode and not self._shared_owner:
                raw_frame = self._read_shared_frame()
                if raw_frame is None:
                    raw_frame = self._build_dummy_frame()
                processed_frame = self._preprocess(raw_frame) if cv2 is not None and np is not None else raw_frame
            elif self._dummy_mode or self._capture is None:
                raw_frame = self._build_dummy_frame()
                processed_frame = self._preprocess(raw_frame) if cv2 is not None and np is not None else raw_frame
            else:
                ok, raw_frame = self._capture.read()
                if not ok:
                    raw_frame = self._build_dummy_frame()
                    processed_frame = raw_frame
                else:
                    self._write_shared_frame(raw_frame)
                    processed_frame = self._preprocess(raw_frame)

            return VideoFrame(
                frame_id=self._frame_id,
                timestamp=timestamp,
                raw_frame=raw_frame,
                processed_frame=processed_frame,
                width=width,
                height=height,
                fps=self.config.fps,
            )

    def is_running(self) -> bool:
        return self.state.running

    def stop(self) -> None:
        with self._lock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None
            if self._shared_owner:
                self._release_shared_camera()
                self._shared_owner = False
            self.state.running = False

    def _claim_shared_camera(self) -> bool:
        lock_path = Path(self.config.shared_lock_path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        try:
            if lock_path.exists():
                age = now - lock_path.stat().st_mtime
                if age <= self.config.shared_stale_seconds:
                    return False
                lock_path.unlink()
            lock_path.write_text(str(now), encoding="utf-8")
            return True
        except OSError:
            return False

    def _release_shared_camera(self) -> None:
        try:
            Path(self.config.shared_lock_path).unlink(missing_ok=True)
        except OSError:
            pass

    def _read_shared_frame(self):
        if cv2 is None:
            return None
        frame_path = Path(self.config.shared_frame_path)
        try:
            if not frame_path.exists():
                return None
            if time.time() - frame_path.stat().st_mtime > self.config.shared_stale_seconds:
                return None
            return cv2.imread(str(frame_path))
        except OSError:
            return None

    def _write_shared_frame(self, frame) -> None:
        if not self.config.shared_mode or cv2 is None:
            return
        frame_path = Path(self.config.shared_frame_path)
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = frame_path.with_suffix(".tmp.jpg")
        try:
            cv2.imwrite(str(tmp_path), frame)
            tmp_path.replace(frame_path)
            Path(self.config.shared_lock_path).touch()
        except OSError:
            pass
