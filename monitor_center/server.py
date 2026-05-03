"""Monitoring center server for TCP alerts/control and UDP video frames."""

from __future__ import annotations

import base64
import json
import queue
import signal
import socket
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Any

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None
    np = None

try:
    from .config import ServerConfig, ensure_data_dirs
    from .database import Database
    from .global_decision import GlobalDecisionEngine
    from .node_manager import NodeInfo, NodeManager
    from .protocol_parser import (
        MessageType,
        ProtocolError,
        ProtocolFrame,
        StreamFrameParser,
        encode_frame,
        looks_like_protocol,
        parse_frame,
    )
except ImportError:  # pragma: no cover
    from config import ServerConfig, ensure_data_dirs
    from database import Database
    from global_decision import GlobalDecisionEngine
    from node_manager import NodeInfo, NodeManager
    from protocol_parser import (
        MessageType,
        ProtocolError,
        ProtocolFrame,
        StreamFrameParser,
        encode_frame,
        looks_like_protocol,
        parse_frame,
    )


class MonitorCenterServer:
    def __init__(self, config: ServerConfig | None = None) -> None:
        ensure_data_dirs()
        self.config = config or ServerConfig()
        self.database = Database()
        self.node_manager = NodeManager(self.database, event_callback=self._record_node_event)
        self.decision_engine = GlobalDecisionEngine()
        self.alert_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)
        self.video_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=100)
        self.latest_frames: dict[str, bytes] = {}
        self.latest_alerts: dict[str, dict[str, Any]] = {}
        self._frames_lock = threading.RLock()
        self._alerts_lock = threading.RLock()
        self._running = threading.Event()
        self._threads: list[threading.Thread] = []
        self._tcp_sockets: list[socket.socket] = []
        self._udp_sockets: list[socket.socket] = []
        self._clients: dict[str, socket.socket] = {}
        self._clients_lock = threading.RLock()
        self._http_server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        self._running.set()
        self.node_manager.start()
        self._threads = [
            *[
                threading.Thread(target=self._tcp_server_loop, args=(port,), name=f"tcp-alert-server-{port}", daemon=True)
                for port in self.config.tcp_ports
            ],
            *[
                threading.Thread(target=self._udp_server_loop, args=(port,), name=f"udp-video-server-{port}", daemon=True)
                for port in self.config.udp_ports
            ],
            threading.Thread(target=self._mjpeg_server_loop, name="mjpeg-server", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def serve_forever(self) -> None:
        self.start()
        print(
            f"Monitoring center started: TCP {self.config.tcp_ports}, "
            f"UDP {self.config.udp_ports}, MJPEG {self.config.mjpeg_port}"
        )
        try:
            while self._running.is_set():
                time.sleep(1.0)
        finally:
            self.stop()

    def stop(self) -> None:
        self._running.clear()
        self.node_manager.stop()
        for sock in [*self._tcp_sockets, *self._udp_sockets]:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        with self._clients_lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            try:
                client.close()
            except OSError:
                pass
        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=2.0)
        self.database.close()

    def send_control_command(self, node_id: str, config: dict[str, Any]) -> bool:
        payload = {"command": "update_config", "config": config, "timestamp": time.time()}
        packet = encode_frame(MessageType.CONTROL, "monitor-center", payload)
        with self._clients_lock:
            client = self._clients.get(node_id)
        if client is None:
            return False
        try:
            client.sendall(packet)
            return True
        except OSError:
            return False

    def _tcp_server_loop(self, port: int) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            self._tcp_sockets.append(server_sock)
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((self.config.host, port))
            server_sock.listen(16)
            server_sock.settimeout(self.config.socket_timeout)
            while self._running.is_set():
                try:
                    client_sock, address = server_sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                thread = threading.Thread(
                    target=self._handle_tcp_client,
                    args=(client_sock, address),
                    name=f"tcp-client-{address[0]}:{address[1]}",
                    daemon=True,
                )
                thread.start()

    def _handle_tcp_client(self, client_sock: socket.socket, address: tuple[str, int]) -> None:
        parser = StreamFrameParser(max_payload_size=self.config.max_tcp_payload_size)
        known_node_id: str | None = None
        client_sock.settimeout(self.config.socket_timeout)
        try:
            while self._running.is_set():
                try:
                    chunk = client_sock.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break

                if looks_like_protocol(chunk) or parser._buffer:
                    try:
                        frames = parser.feed(chunk)
                    except ProtocolError as exc:
                        print(f"Protocol error from {address}: {exc}")
                        continue
                    for frame in frames:
                        known_node_id = frame.node_id or known_node_id
                        self._handle_frame(frame, address, client_sock)
                    continue

                legacy_node_id = self._handle_legacy_tcp(chunk, address, client_sock)
                known_node_id = legacy_node_id or known_node_id
        finally:
            if known_node_id:
                with self._clients_lock:
                    if self._clients.get(known_node_id) is client_sock:
                        self._clients.pop(known_node_id, None)
            try:
                client_sock.close()
            except OSError:
                pass

    def _udp_server_loop(self, port: int) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_sock:
            self._udp_sockets.append(udp_sock)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp_sock.bind((self.config.host, port))
            udp_sock.settimeout(self.config.socket_timeout)
            while self._running.is_set():
                try:
                    datagram, address = udp_sock.recvfrom(self.config.max_udp_payload_size)
                except socket.timeout:
                    continue
                except OSError:
                    break

                try:
                    if looks_like_protocol(datagram):
                        frame = parse_frame(datagram)
                        self._handle_frame(frame, address, None)
                    else:
                        self._handle_legacy_video(datagram, address)
                except ProtocolError as exc:
                    print(f"UDP protocol error from {address}: {exc}")

    def _mjpeg_server_loop(self) -> None:
        owner = self

        class MjpegHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/stream":
                    self.send_error(HTTPStatus.NOT_FOUND, "not found")
                    return
                node_id = parse_qs(parsed.query).get("node_id", [""])[0]
                if not node_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "node_id is required")
                    return

                self.send_response(HTTPStatus.OK)
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()

                while owner._running.is_set():
                    with owner._frames_lock:
                        frame = owner.latest_frames.get(node_id)
                    if frame:
                        frame = owner._annotate_stream_frame(node_id, frame)
                        try:
                            self.wfile.write(b"--frame\r\n")
                            self.wfile.write(b"Content-Type: image/jpeg\r\n")
                            self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                            self.wfile.write(frame)
                            self.wfile.write(b"\r\n")
                            self.wfile.flush()
                        except OSError:
                            break
                    time.sleep(0.1)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._http_server = ThreadingHTTPServer((self.config.host, self.config.mjpeg_port), MjpegHandler)
        self._http_server.serve_forever(poll_interval=0.5)

    def _handle_frame(
        self,
        frame: ProtocolFrame,
        address: tuple[str, int],
        client_sock: socket.socket | None,
    ) -> None:
        ip = address[0]
        payload = self._decode_payload(frame.payload)
        node_type = payload.get("node_type") if isinstance(payload, dict) else None

        if frame.msg_type == MessageType.REGISTER:
            self.node_manager.register_node(frame.node_id, ip, node_type)
            if client_sock is not None:
                with self._clients_lock:
                    self._clients[frame.node_id] = client_sock
            return

        if frame.msg_type == MessageType.HEARTBEAT:
            self.node_manager.heartbeat(frame.node_id, ip, node_type)
            return

        self.node_manager.heartbeat(frame.node_id, ip, node_type)
        if client_sock is not None:
            with self._clients_lock:
                self._clients[frame.node_id] = client_sock

        if frame.msg_type == MessageType.ALERT:
            self._handle_alert(frame.node_id, payload)
        elif frame.msg_type == MessageType.VIDEO:
            self._handle_video(frame.node_id, frame.payload, payload if isinstance(payload, dict) else None)
        elif frame.msg_type == MessageType.INFERENCE:
            self._handle_inference(frame.node_id, payload)
        elif frame.msg_type == MessageType.CONTROL:
            target_node = str(payload.get("target_node", ""))
            command_config = payload.get("config", {})
            if target_node and isinstance(command_config, dict):
                sent = self.send_control_command(target_node, command_config)
                print(f"control command target={target_node} sent={sent}")

    def _handle_alert(self, node_id: str, payload: dict[str, Any]) -> None:
        alert_type = str(payload.get("alert_type", payload.get("type", "unknown")))
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        bbox = _coerce_bbox(payload.get("bbox"))
        timestamp = _payload_timestamp(payload)
        decision = self.decision_engine.evaluate(node_id, alert_type, confidence, timestamp)
        record = {
            "node_id": node_id,
            "alert_type": alert_type,
            "confidence": confidence,
            "timestamp": datetime.fromtimestamp(timestamp).isoformat(timespec="seconds"),
            "screenshot_path": None,
            "level": decision.level,
            "description": payload.get("description") or decision.reason,
            "bbox": bbox,
        }
        if decision.duplicate:
            with self._alerts_lock:
                previous = self.latest_alerts.get(node_id)
                if previous:
                    record["level"] = str(previous.get("level", "normal"))
                    record["description"] = str(previous.get("description", decision.reason))
                    if not record["bbox"]:
                        record["bbox"] = _coerce_bbox(previous.get("bbox"))
        with self._alerts_lock:
            self.latest_alerts[node_id] = record
        if decision.duplicate:
            return
        self.database.insert_alert(**record)
        _queue_put_latest(self.alert_queue, record)

    def _handle_video(self, node_id: str, raw_payload: bytes, decoded_payload: dict[str, Any] | None = None) -> None:
        frame_bytes = raw_payload
        if decoded_payload and "frame" in decoded_payload:
            try:
                frame_bytes = base64.b64decode(decoded_payload["frame"])
            except Exception:
                return
        with self._frames_lock:
            self.latest_frames[node_id] = frame_bytes
        _queue_put_latest(self.video_queue, {"node_id": node_id, "timestamp": time.time(), "frame_bytes": frame_bytes})

    def _handle_inference(self, node_id: str, payload: dict[str, Any]) -> None:
        if payload.get("has_abnormal") and payload.get("targets"):
            best = max(payload["targets"], key=lambda item: float(item.get("confidence", 0.0)))
            alert_payload = {
                "alert_type": best.get("class_name", "abnormal"),
                "confidence": best.get("confidence", 0.0),
                "bbox": best.get("bbox"),
                "description": "inference abnormal result",
            }
            self._handle_alert(node_id, alert_payload)

    def _handle_legacy_tcp(self, chunk: bytes, address: tuple[str, int], client_sock: socket.socket) -> str | None:
        try:
            payload = json.loads(chunk.decode("utf-8"))
        except Exception:
            return None
        node_id = str(payload.get("node_id", f"legacy-{address[0]}"))
        self.node_manager.heartbeat(node_id, address[0], payload.get("node_type"))
        with self._clients_lock:
            self._clients[node_id] = client_sock
        if "alert_type" in payload:
            self._handle_alert(node_id, payload)
        elif payload.get("type") == "register":
            self.node_manager.register_node(node_id, address[0], payload.get("node_type"))
        return node_id

    def _handle_legacy_video(self, datagram: bytes, address: tuple[str, int]) -> None:
        node_id = f"legacy-{address[0]}"
        self.node_manager.heartbeat(node_id, address[0], "video")
        _queue_put_latest(self.video_queue, {"node_id": node_id, "timestamp": time.time(), "frame_bytes": datagram})

    def _decode_payload(self, payload: bytes) -> dict[str, Any]:
        try:
            return json.loads(payload.decode("utf-8")) if payload else {}
        except Exception:
            return {}

    def _record_node_event(self, event: str, node: NodeInfo) -> None:
        print(f"[{datetime.now().isoformat(timespec='seconds')}] node {event}: {node.node_id} ({node.ip})")

    def _annotate_stream_frame(self, node_id: str, frame_bytes: bytes) -> bytes:
        if cv2 is None or np is None:
            return frame_bytes

        alert = self._current_alert_for_node(node_id)
        if alert is None:
            return frame_bytes

        frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
        image = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if image is None:
            return frame_bytes

        level = str(alert.get("level", "normal"))
        alert_type = str(alert.get("alert_type", "alert"))
        confidence = float(alert.get("confidence", 0.0) or 0.0)
        color = (0, 0, 255) if level in {"critical", "high"} else (0, 165, 255)

        height, width = image.shape[:2]
        bbox = _coerce_bbox(alert.get("bbox"), width=width, height=height)
        if bbox is None:
            return frame_bytes

        x1, y1, x2, y2 = bbox
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
        label = f"{alert_type} | {confidence:.2f}"
        label_y = y1 - 10 if y1 >= 22 else y2 + 24
        label_y = max(18, min(height - 8, label_y))
        text_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        text_w, text_h = text_size
        text_x = max(0, min(width - text_w - 8, x1))
        box_top = max(0, label_y - text_h - baseline - 6)
        box_bottom = min(height - 1, label_y + baseline + 4)
        cv2.rectangle(image, (text_x, box_top), (min(width - 1, text_x + text_w + 8), box_bottom), color, -1)
        cv2.putText(
            image,
            label,
            (text_x + 4, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            return frame_bytes
        return encoded.tobytes()

    def _current_alert_for_node(self, node_id: str) -> dict[str, Any] | None:
        with self._alerts_lock:
            alert = self.latest_alerts.get(node_id)
        if not alert:
            return None
        try:
            alert_dt = datetime.fromisoformat(str(alert.get("timestamp")))
        except ValueError:
            return alert
        age = time.time() - alert_dt.timestamp()
        if age > self.config.alert_overlay_seconds:
            return None
        return alert


def _coerce_bbox(raw: Any, width: int | None = None, height: int | None = None) -> list[int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in raw]
    except (TypeError, ValueError):
        return None

    if width and height and max(x1, y1, x2, y2) <= 1.0:
        x1 *= width
        x2 *= width
        y1 *= height
        y2 *= height

    if width is not None:
        x1 = max(0.0, min(x1, width - 1))
        x2 = max(0.0, min(x2, width - 1))
    if height is not None:
        y1 = max(0.0, min(y1, height - 1))
        y2 = max(0.0, min(y2, height - 1))

    left = int(round(min(x1, x2)))
    top = int(round(min(y1, y2)))
    right = int(round(max(x1, x2)))
    bottom = int(round(max(y1, y2)))
    if right <= left or bottom <= top:
        return None
    return [left, top, right, bottom]


def _payload_timestamp(payload: dict[str, Any]) -> float:
    raw = payload.get("timestamp")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw).timestamp()
        except ValueError:
            pass
    return time.time()


def _queue_put_latest(target: queue.Queue[dict[str, Any]], item: dict[str, Any]) -> None:
    try:
        target.put_nowait(item)
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        target.put_nowait(item)


def main() -> None:
    server = MonitorCenterServer()

    def _shutdown(signum: int, frame: object) -> None:
        server.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    server.serve_forever()


if __name__ == "__main__":
    main()
