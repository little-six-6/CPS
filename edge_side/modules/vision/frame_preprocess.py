"""Frame preprocessing helpers for module 1."""

from __future__ import annotations

from typing import Any

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None


def resize_frame(frame: Any, width: int, height: int) -> Any:
    if cv2 is None or np is None:
        return frame
    return cv2.resize(frame, (width, height))


def to_gray(frame: Any) -> Any:
    if cv2 is None or np is None:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
