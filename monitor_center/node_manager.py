"""Node registry, status tracking, and heartbeat monitoring."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Callable

try:
    from .config import DEFAULT_NODE_TYPES, NodeConfig
    from .database import Database
except ImportError:  # pragma: no cover
    from config import DEFAULT_NODE_TYPES, NodeConfig
    from database import Database


@dataclass
class NodeInfo:
    node_id: str
    ip: str
    node_type: str
    status: str
    last_seen: float

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["last_seen_iso"] = datetime.fromtimestamp(self.last_seen).isoformat(timespec="seconds")
        return data


class NodeManager:
    def __init__(
        self,
        database: Database,
        config: NodeConfig | None = None,
        event_callback: Callable[[str, NodeInfo], None] | None = None,
    ) -> None:
        self.database = database
        self.config = config or NodeConfig()
        self.event_callback = event_callback
        self._nodes: dict[str, NodeInfo] = {}
        self._lock = threading.RLock()
        self._running = False
        self._thread: threading.Thread | None = None

    def register_node(self, node_id: str, ip: str, node_type: str | None = None) -> NodeInfo:
        node_type = node_type or DEFAULT_NODE_TYPES.get(node_id, "unknown")
        now = time.time()
        event: str | None = None
        with self._lock:
            existing = self._nodes.get(node_id)
            if existing is None:
                node = NodeInfo(node_id=node_id, ip=ip, node_type=node_type, status="online", last_seen=now)
                self._nodes[node_id] = node
                event = "online"
            else:
                was_offline = existing.status != "online"
                existing.ip = ip
                existing.node_type = node_type
                existing.status = "online"
                existing.last_seen = now
                node = existing
                if was_offline:
                    event = "online"

            self.database.upsert_node(
                node_id=node.node_id,
                ip=node.ip,
                node_type=node.node_type,
                status=node.status,
                last_seen=datetime.fromtimestamp(node.last_seen).isoformat(timespec="seconds"),
            )

        if event:
            self._emit(event, node)
        return node

    def heartbeat(self, node_id: str, ip: str, node_type: str | None = None) -> NodeInfo:
        return self.register_node(node_id=node_id, ip=ip, node_type=node_type)

    def mark_offline(self, node_id: str) -> None:
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None or node.status == "offline":
                return
            node.status = "offline"
            self.database.update_node_status(
                node_id=node.node_id,
                status=node.status,
                last_seen=datetime.fromtimestamp(node.last_seen).isoformat(timespec="seconds"),
            )
        self._emit("offline", node)

    def get_node(self, node_id: str) -> NodeInfo | None:
        with self._lock:
            return self._nodes.get(node_id)

    def list_nodes(self) -> list[dict[str, object]]:
        with self._lock:
            return [node.to_dict() for node in sorted(self._nodes.values(), key=lambda item: item.node_id)]

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _heartbeat_loop(self) -> None:
        while self._running:
            now = time.time()
            offline_ids: list[str] = []
            with self._lock:
                for node in self._nodes.values():
                    if node.status == "online" and now - node.last_seen > self.config.offline_timeout_seconds:
                        offline_ids.append(node.node_id)
            for node_id in offline_ids:
                self.mark_offline(node_id)
            time.sleep(1.0)

    def _emit(self, event: str, node: NodeInfo) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback(event, node)
        except Exception:
            pass

