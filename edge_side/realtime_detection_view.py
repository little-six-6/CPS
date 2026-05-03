"""Realtime camera viewer with detection overlays.

Run from the edge_side directory:

    python realtime_detection_view.py

Press `q` or `Esc` to quit.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.pipeline import EdgePipeline  # noqa: E402


def _normalize_color(class_name: str) -> tuple[int, int, int]:
    if class_name in {"fire", "smoke", "cigarette", "smoking", "no_hardhat", "fall"}:
        return (0, 0, 255)
    if class_name == "helmet":
        return (0, 200, 0)
    if class_name == "person":
        return (255, 255, 0)
    return (255, 255, 255)


def _clamp_bbox(bbox, width: int, height: int) -> tuple[int, int, int, int] | None:
    try:
        x1, y1, x2, y2 = [int(round(v)) for v in bbox]
    except Exception:
        return None

    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(x1 + 1, min(width - 1, x2))
    y2 = max(y1 + 1, min(height - 1, y2))
    return x1, y1, x2, y2


def _draw_label(image, text: str, origin: tuple[int, int], color: tuple[int, int, int]) -> None:
    if cv2 is None:
        return

    x, y = origin
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.5
    thickness = 1
    (text_width, text_height), baseline = cv2.getTextSize(text, font, scale, thickness)
    pad_x = 6
    pad_y = 4
    top_left = (x, max(0, y - text_height - baseline - pad_y * 2))
    bottom_right = (x + text_width + pad_x * 2, y)
    cv2.rectangle(image, top_left, bottom_right, color, -1)
    cv2.putText(
        image,
        text,
        (x + pad_x, y - pad_y - baseline),
        font,
        scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def _draw_overlay(frame, detections, alert_packet=None, backend: str | None = None, backend_error: str | None = None):
    if cv2 is None or frame is None or not hasattr(frame, "copy"):
        return frame

    image = frame.copy()
    height, width = image.shape[:2]

    det_list = list(detections or [])
    summary_items: list[str] = []

    for target in det_list:
        try:
            bbox = _clamp_bbox(target.bbox, width, height)
            if bbox is None:
                continue
            x1, y1, x2, y2 = bbox
            color = _normalize_color(target.class_name)
            label = f"{target.class_name} {target.confidence:.2f}"
            source = f"{target.source_model}" if target.source_model else ""
            if source:
                label = f"{source}:{label}"
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            _draw_label(image, label, (x1, max(18, y1 + 18)), color)
            summary_items.append(f"{target.class_name}:{target.confidence:.2f}")
        except Exception:
            continue

    if backend:
        backend_text = f"backend: {backend}"
        if backend_error and backend != "local-multi-yolo":
            backend_text = f"{backend_text} | {backend_error[:60]}"
        cv2.rectangle(image, (8, 8), (min(width - 8, 18 + max(len(backend_text), 20) * 8), 42), (0, 0, 0), -1)
        cv2.putText(
            image,
            backend_text,
            (14, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    elif summary_items:
        panel_text = " | ".join(summary_items[:4])
        cv2.rectangle(image, (8, 8), (min(width - 8, 18 + len(panel_text) * 10), 42), (0, 0, 0), -1)
        cv2.putText(
            image,
            f"Detections: {panel_text}",
            (14, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    else:
        cv2.rectangle(image, (8, 8), (170, 42), (0, 0, 0), -1)
        cv2.putText(
            image,
            "Detections: none",
            (14, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    if alert_packet is not None:
        header = f"ALERT: {alert_packet.alert_type} | {alert_packet.alert_level} | {alert_packet.confidence:.2f}"
        cv2.rectangle(image, (8, 46), (min(width - 8, 18 + len(header) * 10), 86), (0, 0, 180), -1)
        cv2.putText(
            image,
            header,
            (14, 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            alert_packet.description[:80],
            (14, 98),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )

    return image


def main() -> int:
    if cv2 is None:
        print("OpenCV is not installed. Please install opencv-python first.")
        return 1

    pipeline = EdgePipeline()
    pipeline.start()

    try:
        print("Realtime viewer started. Press q or Esc to quit.")
        while True:
            pipeline.step()
            frame = pipeline.last_frame.raw_frame if pipeline.last_frame else None
            detections = pipeline.last_inference.targets if pipeline.last_inference else []
            backend = pipeline.detector.loader.last_backend
            backend_error = pipeline.detector.loader.last_error
            annotated = _draw_overlay(frame, detections, pipeline.last_alert_packet, backend, backend_error)
            if annotated is not None:
                cv2.imshow("Edge Side Detection", annotated)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

        return 0
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
