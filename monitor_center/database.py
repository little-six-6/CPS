"""SQLite storage for nodes, alerts, and statistics."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .config import DB_PATH, ensure_data_dirs
except ImportError:  # pragma: no cover
    from config import DB_PATH, ensure_data_dirs


class Database:
    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        ensure_data_dirs()
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    ip TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    screenshot_path TEXT,
                    bbox TEXT,
                    level TEXT NOT NULL DEFAULT 'normal',
                    description TEXT
                );

                CREATE TABLE IF NOT EXISTS statistics (
                    date TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY (date, alert_type)
                );

                CREATE INDEX IF NOT EXISTS idx_alert_logs_timestamp ON alert_logs(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_alert_logs_node_id ON alert_logs(node_id);
                """
            )
            columns = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(alert_logs)").fetchall()
            }
            if "bbox" not in columns:
                self._conn.execute("ALTER TABLE alert_logs ADD COLUMN bbox TEXT")

    @staticmethod
    def now_iso() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def upsert_node(self, node_id: str, ip: str, node_type: str, status: str, last_seen: str | None = None) -> None:
        last_seen = last_seen or self.now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO nodes (node_id, ip, node_type, status, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    ip = excluded.ip,
                    node_type = excluded.node_type,
                    status = excluded.status,
                    last_seen = excluded.last_seen
                """,
                (node_id, ip, node_type, status, last_seen),
            )

    def update_node_status(self, node_id: str, status: str, last_seen: str | None = None) -> None:
        last_seen = last_seen or self.now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE nodes SET status = ?, last_seen = ? WHERE node_id = ?",
                (status, last_seen, node_id),
            )

    def insert_alert(
        self,
        node_id: str,
        alert_type: str,
        confidence: float,
        timestamp: str | None = None,
        screenshot_path: str | None = None,
        bbox: list[float] | None = None,
        level: str = "normal",
        description: str | None = None,
    ) -> int:
        timestamp = timestamp or self.now_iso()
        alert_date = timestamp[:10]
        bbox_json = json.dumps(bbox, ensure_ascii=False) if bbox else None
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO alert_logs
                    (node_id, alert_type, confidence, timestamp, screenshot_path, bbox, level, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (node_id, alert_type, confidence, timestamp, screenshot_path, bbox_json, level, description),
            )
            self._conn.execute(
                """
                INSERT INTO statistics (date, alert_type, count)
                VALUES (?, ?, 1)
                ON CONFLICT(date, alert_type) DO UPDATE SET count = count + 1
                """,
                (alert_date, alert_type),
            )
            return int(cur.lastrowid)

    def list_nodes(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM nodes ORDER BY node_id").fetchall()
            return [dict(row) for row in rows]

    def list_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM alert_logs ORDER BY timestamp DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def query_alerts(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        node_id: str | None = None,
        alert_type: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if start_date:
            clauses.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("timestamp <= ?")
            params.append(end_date)
        if node_id:
            clauses.append("node_id = ?")
            params.append(node_id)
        if alert_type:
            clauses.append("alert_type = ?")
            params.append(alert_type)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM alert_logs {where_sql} ORDER BY timestamp DESC, id DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def list_statistics(self, days: int = 14) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT date, alert_type, count
                FROM statistics
                ORDER BY date DESC, alert_type
                LIMIT ?
                """,
                (days * 20,),
            ).fetchall()
            return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
