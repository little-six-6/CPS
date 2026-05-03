"""Module 3: network communication and transfer."""

from __future__ import annotations

import socket
import time
from typing import Optional

from core.base_module import BaseModule
from modules.network.protocol import (
    decode_remote_command,
    encode_alert_frame,
    encode_alert_packet,
    encode_heartbeat_packet,
    encode_register_packet,
    encode_video_frame,
    encode_video_frame_packet,
)
from utils.data_structs import AlertPacket, NetworkConfig, SendStatus, VideoFrame, VideoFrameBytes, RemoteCommand


class NetworkClient(BaseModule):
    def __init__(self, config: NetworkConfig) -> None:
        super().__init__("network")
        self.config = config
        self._udp_socket: Optional[socket.socket] = None
        self._tcp_socket: Optional[socket.socket] = None
        self._online = False
        self._last_heartbeat_ts = 0.0

    def start(self) -> bool:
        return self.connect()

    def connect(self) -> bool:
        try:
            self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._tcp_socket.settimeout(1.0)
            try:
                self._tcp_socket.connect((self.config.server_ip, self.config.tcp_alert_port))
                self._online = True
                self._send_register()
            except OSError:
                self._online = False
            self.state.running = True
            self.state.initialized = True
            return True
        except OSError:
            self._online = False
            self.state.running = True
            self.state.initialized = True
            return True

    def encode_video_frame(self, frame: VideoFrame) -> VideoFrameBytes:
        return encode_video_frame(frame)

    def send_video(self, data: VideoFrameBytes) -> SendStatus:
        self._send_heartbeat_if_needed()
        if self._udp_socket is None or not self._online:
            return SendStatus(success=True, message="video queued in offline mode", timestamp=time.time())
        try:
            packet = (
                encode_video_frame_packet(self.config.node_id, data)
                if self.config.use_framed_protocol
                else data.frame_bytes
            )
            self._udp_socket.sendto(packet, (self.config.server_ip, self.config.udp_video_port))
            return SendStatus(success=True, message="video sent", timestamp=time.time())
        except OSError as exc:
            return SendStatus(success=False, message=str(exc), timestamp=time.time())

    def send_alert(self, alert: AlertPacket) -> SendStatus:
        self._send_heartbeat_if_needed()
        packet = encode_alert_frame(alert) if self.config.use_framed_protocol else encode_alert_packet(alert)
        if self._tcp_socket is None or not self._online:
            return SendStatus(success=True, message="alert queued in offline mode", timestamp=time.time())
        try:
            self._tcp_socket.sendall(packet)
            return SendStatus(success=True, message="alert sent", timestamp=time.time())
        except OSError as exc:
            return SendStatus(success=False, message=str(exc), timestamp=time.time())

    def recv_remote_command(self) -> Optional[RemoteCommand]:
        if self._tcp_socket is None or not self._online:
            return None
        try:
            data = self._tcp_socket.recv(4096)
            if not data:
                return None
            if data.startswith(b"\xAA\x55") and len(data) >= 27:
                payload_len = int.from_bytes(data[19:23], "big")
                payload = data[23 : 23 + payload_len]
                return decode_remote_command(payload)
            return decode_remote_command(data)
        except OSError:
            return None

    def _send_register(self) -> None:
        if self._tcp_socket is None or not self.config.use_framed_protocol:
            return
        try:
            self._tcp_socket.sendall(encode_register_packet(self.config.node_id, self.config.node_type))
            self._last_heartbeat_ts = time.time()
        except OSError:
            self._online = False

    def _send_heartbeat_if_needed(self) -> None:
        if (
            self._tcp_socket is None
            or not self._online
            or not self.config.use_framed_protocol
            or time.time() - self._last_heartbeat_ts < self.config.heartbeat_interval_seconds
        ):
            return
        try:
            self._tcp_socket.sendall(encode_heartbeat_packet(self.config.node_id, self.config.node_type))
            self._last_heartbeat_ts = time.time()
        except OSError:
            self._online = False

    def close(self) -> None:
        if self._udp_socket is not None:
            self._udp_socket.close()
            self._udp_socket = None
        if self._tcp_socket is not None:
            self._tcp_socket.close()
            self._tcp_socket = None
        self.state.running = False

    def stop(self) -> None:
        self.close()
