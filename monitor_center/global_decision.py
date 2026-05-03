"""Global alert decision logic."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

try:
    from .config import DecisionConfig
except ImportError:  # pragma: no cover
    from config import DecisionConfig


@dataclass(frozen=True)
class DecisionResult:
    should_display: bool
    level: str
    reason: str
    duplicate: bool = False


class GlobalDecisionEngine:
    def __init__(self, config: DecisionConfig | None = None) -> None:
        self.config = config or DecisionConfig()
        self._recent_by_type: dict[str, float] = {}
        self._active_alerts: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def evaluate(self, node_id: str, alert_type: str, confidence: float, timestamp: float | None = None) -> DecisionResult:
        now = timestamp or time.time()
        with self._lock:
            last_same_type = self._recent_by_type.get(alert_type)
            if last_same_type is not None and now - last_same_type < self.config.dedupe_window_seconds:
                return DecisionResult(
                    should_display=False,
                    level="duplicate",
                    reason=f"{alert_type} duplicated within {self.config.dedupe_window_seconds}s",
                    duplicate=True,
                )

            cutoff = now - self.config.multi_alert_window_seconds
            self._active_alerts = [item for item in self._active_alerts if item["timestamp"] >= cutoff]
            distinct_nodes = {item["node_id"] for item in self._active_alerts}
            distinct_nodes.add(node_id)

            level = "normal"
            reason = "single node alert"
            if len(distinct_nodes) >= 2:
                level = "critical"
                reason = "multiple nodes alerting within decision window"
            elif confidence >= 0.9:
                level = "high"
                reason = "high confidence alert"

            self._recent_by_type[alert_type] = now
            self._active_alerts.append(
                {"node_id": node_id, "alert_type": alert_type, "confidence": confidence, "timestamp": now}
            )
            return DecisionResult(should_display=True, level=level, reason=reason)

