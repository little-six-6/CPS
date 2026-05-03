"""Common runner for single-detection edge nodes."""

from __future__ import annotations

import argparse
import importlib
import time
from pathlib import Path
from typing import Optional

from core.pipeline import EdgePipeline
from utils.constants import DEFAULT_INTERVAL_SECONDS


def parse_args(default_node: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Run {default_node} single-detection edge node.")
    parser.add_argument("--camera-id", type=int, default=None, help="Override camera id. Default uses config value.")
    parser.add_argument("--iterations", type=int, default=0, help="Number of cycles. 0 means run forever.")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS, help="Loop interval in seconds.")
    parser.add_argument("--server-ip", type=str, default=None, help="Override monitoring center IP.")
    return parser.parse_args()


def run(config_module: str, default_node: str) -> int:
    args = parse_args(default_node)
    cfg = importlib.import_module(config_module)
    camera_config = cfg.CAMERA_CONFIG
    network_config = cfg.NETWORK_CONFIG

    if args.camera_id is not None:
        camera_config.camera_id = args.camera_id
    if args.server_ip:
        network_config.server_ip = args.server_ip

    pipeline = EdgePipeline(
        camera_config=camera_config,
        model_config=cfg.MODEL_CONFIG,
        alert_config=cfg.ALERT_CONFIG,
        network_config=network_config,
    )
    iterations: Optional[int] = None if args.iterations == 0 else args.iterations
    print(f"cwd={Path.cwd()}")
    print(
        f"starting node={network_config.node_id} type={network_config.node_type} "
        f"udp={network_config.udp_video_port} tcp={network_config.tcp_alert_port}"
    )
    print(
        f"camera: id={camera_config.camera_id} shared_mode={camera_config.shared_mode} "
        f"shared_frame={camera_config.shared_frame_path} shared_lock={camera_config.shared_lock_path}"
    )
    print(
        f"model: path={pipeline.detector.config.model_path} "
        f"threshold={pipeline.detector.config.conf_threshold} active={pipeline.detector.config.active_model_aliases}"
    )
    print(
        f"alert: threshold={pipeline.alert_engine.config.alert_conf_threshold} "
        f"consecutive={pipeline.alert_engine.config.consecutive_frames} cooldown={pipeline.alert_engine.config.cooldown_seconds}"
    )

    pipeline.start()
    print(
        f"network_online={getattr(pipeline.network, '_online', None)} "
        f"camera_running={pipeline.camera.is_running()} "
        f"dummy_mode={getattr(pipeline.camera, '_dummy_mode', None)} "
        f"shared_owner={getattr(pipeline.camera, '_shared_owner', None)}"
    )
    last_backend: str | None = None
    last_error: str | None = None
    count = 0
    try:
        while iterations is None or count < iterations:
            step_started = time.time()
            pipeline.step()
            count += 1
            backend = pipeline.detector.loader.last_backend
            error = pipeline.detector.loader.last_error
            if count <= 5 or backend != last_backend or error != last_error or count % 20 == 0:
                print(
                    f"step={count} frames={pipeline.stats.frames} alerts={pipeline.stats.alerts} errors={pipeline.stats.errors} "
                    f"backend={backend} model={pipeline.detector.loader.last_model_id or 'n/a'} "
                    f"predictions={pipeline.detector.loader.last_prediction_count} error={error or 'none'} "
                    f"has_abnormal={pipeline.last_inference.has_abnormal if pipeline.last_inference else None}"
                )
                print(
                    f"  frame_id={pipeline.last_frame.frame_id if pipeline.last_frame else None} "
                    f"frame_ts={pipeline.last_frame.timestamp if pipeline.last_frame else None} "
                    f"alert={pipeline.last_alert_packet.alert_type if pipeline.last_alert_packet else None}"
                )
            last_backend = backend
            last_error = error
            elapsed = time.time() - step_started
            time.sleep(max(0.0, args.interval - elapsed))
    finally:
        pipeline.stop()
    stats = pipeline.stats
    print(f"node finished: frames={stats.frames}, alerts={stats.alerts}, errors={stats.errors}")
    return 0
