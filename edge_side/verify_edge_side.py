"""Smoke test for the edge-side pipeline.

Run this file from the edge_side directory:

    python verify_edge_side.py

It validates that the edge pipeline can initialize and execute several
end-to-end steps in offline/degraded mode without real camera, model, or
server dependencies.
"""

from __future__ import annotations

from pathlib import Path
import sys

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.pipeline import EdgePipeline  # noqa: E402


def _draw_detections(frame, detections, output_path: Path) -> None:
    if cv2 is None or frame is None or not hasattr(frame, "copy"):
        return

    image = frame.copy()
    for target in detections:
        try:
            x1, y1, x2, y2 = [int(round(v)) for v in target.bbox]
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = max(x1 + 1, x2)
            y2 = max(y1 + 1, y2)
            color = (0, 255, 0)
            if target.class_name in {"fire", "smoke", "cigarette", "no_hardhat", "no_helmet", "fall"}:
                color = (0, 0, 255)
            elif target.class_name == "person":
                color = (255, 255, 0)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            label = f"{target.source_model}:{target.class_name} {target.confidence:.2f}"
            cv2.putText(
                image,
                label,
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
                cv2.LINE_AA,
            )
        except Exception:
            continue

    cv2.imwrite(str(output_path), image)


def main() -> int:
    pipeline = EdgePipeline()
    pipeline.start()
    output_dir = ROOT / "verify_outputs"
    output_dir.mkdir(exist_ok=True)

    try:
        print("edge-side smoke test starting")
        print("fallback model path:", pipeline.detector.config.model_path)
        print("active models:")
        for alias, path in pipeline.detector.config.local_model_paths.items():
            print(f"  - {alias}: {path}")
        print("label mapping:")
        for alias, mapping in pipeline.detector.config.label_alias_map.items():
            print(f"  - {alias}: {mapping}")
        print("opencv available:", pipeline.camera.is_running())

        initial_frames = pipeline.stats.frames
        initial_alerts = pipeline.stats.alerts

        for _ in range(5):
            pipeline.step()
            loader = pipeline.detector.loader
            step_index = pipeline.stats.frames
            if pipeline.last_frame is not None and pipeline.last_inference is not None:
                annotated_path = output_dir / f"step_{step_index:02d}.jpg"
                _draw_detections(pipeline.last_frame.raw_frame, pipeline.last_inference.targets, annotated_path)
                print(f"  annotated image: {annotated_path}")
            print(
                f"step {pipeline.stats.frames}: backend={loader.last_backend}, "
                f"model={loader.last_model_id or 'n/a'}, "
                f"predictions={loader.last_prediction_count}, "
                f"error={loader.last_error or 'none'}"
            )
            if pipeline.last_inference and pipeline.last_inference.targets:
                for target in pipeline.last_inference.targets:
                    if target.class_name == "other":
                        continue
                    print(
                        f"  target source={target.source_model or 'n/a'}, "
                        f"raw={target.raw_class_name or target.class_name}, "
                        f"class={target.class_name}, "
                        f"confidence={target.confidence:.3f}, "
                        f"bbox={target.bbox}"
                    )
            else:
                print("  no targets returned")
            if pipeline.last_alert_packet:
                print(
                    f"  alert type={pipeline.last_alert_packet.alert_type}, "
                    f"level={pipeline.last_alert_packet.alert_level}, "
                    f"confidence={pipeline.last_alert_packet.confidence:.3f}"
                )

        final_frames = pipeline.stats.frames
        final_alerts = pipeline.stats.alerts

        print("edge-side smoke test passed")
        print(f"frames:  {initial_frames} -> {final_frames}")
        print(f"alerts:  {initial_alerts} -> {final_alerts}")
        print(f"camera running:   {pipeline.camera.is_running()}")
        print(f"detector running:  {pipeline.detector.state.running}")
        print(f"alert running:     {pipeline.alert_engine.state.running}")
        print(f"network running:   {pipeline.network.state.running}")
        print("model backend:", pipeline.detector.loader.last_backend)
        print("last model id:", pipeline.detector.loader.last_model_id or "n/a")

        if final_frames - initial_frames != 5:
            print("frame counter check failed", file=sys.stderr)
            return 1

        return 0
    finally:
        pipeline.stop()


if __name__ == "__main__":
    raise SystemExit(main())
