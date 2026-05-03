"""Smoke test that runs all four node configurations for a few iterations."""

from __future__ import annotations

import importlib

from core.pipeline import EdgePipeline


CONFIG_MODULES = [
    "config.fire_config",
    "config.smoking_config",
    "config.ppe_config",
    "config.fall_config",
]


def main() -> int:
    for module_name in CONFIG_MODULES:
        cfg = importlib.import_module(module_name)
        pipeline = EdgePipeline(
            camera_config=cfg.CAMERA_CONFIG,
            model_config=cfg.MODEL_CONFIG,
            alert_config=cfg.ALERT_CONFIG,
            network_config=cfg.NETWORK_CONFIG,
        )
        stats = pipeline.run(iterations=2, interval=0.05)
        print(
            f"{cfg.NETWORK_CONFIG.node_id}: frames={stats.frames}, alerts={stats.alerts}, "
            f"backend={pipeline.detector.loader.last_backend}, error={pipeline.detector.loader.last_error or 'none'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

