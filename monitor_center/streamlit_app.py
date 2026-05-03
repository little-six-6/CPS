"""Streamlit dashboard for the monitoring center."""

from __future__ import annotations

import html
import json
import socket
import sys
import time
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DB_PATH, DEFAULT_NODE_TYPES, ServerConfig, VIDEO_FRAME_DIR, ensure_data_dirs  # noqa: E402
from database import Database  # noqa: E402
from protocol_parser import MessageType, encode_frame  # noqa: E402


st.set_page_config(
    page_title="智能车间安全监控中心",
    page_icon="◎",
    layout="wide",
    initial_sidebar_state="collapsed",
)
ensure_data_dirs()


NODE_LABELS = {
    "fire_smoke": "火焰烟雾",
    "smoking": "吸烟检测",
    "helmet": "安全帽",
    "fall": "跌倒检测",
}

NODE_PORTS = {
    "fire-smoke-001": "UDP 5000 / TCP 5001",
    "smoking-001": "UDP 5002 / TCP 5003",
    "helmet-001": "UDP 5004 / TCP 5005",
    "fall-001": "UDP 5006 / TCP 5007",
}

LEVEL_META = {
    "critical": ("严重", "critical"),
    "high": ("高危", "high"),
    "normal": ("普通", "normal"),
}


@st.cache_resource
def get_database() -> Database:
    return Database(DB_PATH)


def send_control_command(node_id: str, payload: dict[str, Any]) -> bool:
    packet = encode_frame(MessageType.CONTROL, "monitor-center", payload)
    try:
        with socket.create_connection(("127.0.0.1", ServerConfig().tcp_ports[0]), timeout=2.0) as sock:
            sock.sendall(encode_frame(MessageType.REGISTER, "monitor-ui", {"node_type": "monitor_ui"}))
            sock.sendall(packet)
        return True
    except OSError:
        return False


def latest_frame_path(node_id: str) -> Path | None:
    safe_node_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in node_id)
    files = sorted(VIDEO_FRAME_DIR.glob(f"{safe_node_id}_*.jpg"), key=lambda item: item.stat().st_mtime, reverse=True)
    return files[0] if files else None


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def short_time(value: object) -> str:
    if not value:
        return "-"
    text = str(value)
    try:
        return datetime.fromisoformat(text).strftime("%H:%M:%S")
    except ValueError:
        return text[-8:] if len(text) >= 8 else text


def parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def node_is_online(node: dict[str, Any] | None, stale_seconds: int = 30) -> bool:
    if not node or node.get("status") != "online":
        return False
    last_seen = parse_timestamp(node.get("last_seen"))
    if last_seen is None:
        return False
    return (datetime.now() - last_seen).total_seconds() <= stale_seconds


def frame_age_seconds(node_id: str) -> float | None:
    frame_path = latest_frame_path(node_id)
    if frame_path is None or not frame_path.exists():
        return None
    try:
        return max(0.0, time.time() - frame_path.stat().st_mtime)
    except OSError:
        return None


def port_is_open(port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def backend_status() -> tuple[str, bool]:
    config = ServerConfig()
    required_ports = [config.mjpeg_port, *config.tcp_ports]
    ok = all(port_is_open(port) for port in required_ports)
    return ("运行中" if ok else "未连接", ok)


def inject_css() -> None:
    st.markdown(
        """
<style>
:root {
    --bg-0: #edf4fb;
    --panel: rgba(248, 251, 255, 0.92);
    --line: rgba(77, 116, 154, 0.18);
    --text: #13283d;
    --muted: #60768b;
    --blue: #1d7fb8;
    --green: #1f9d72;
    --amber: #c7811d;
    --red: #d84d4d;
    --radius: 14px;
}

.stApp {
    background:
        radial-gradient(circle at top left, rgba(110, 169, 214, 0.32), transparent 34rem),
        linear-gradient(135deg, #eef6fb 0%, #dfeaf3 48%, #f7fafc 100%);
    color: var(--text);
}

.block-container {
    padding: 0.45rem 0.55rem 1rem;
    max-width: none;
    width: 100%;
}

#MainMenu, footer, header { visibility: hidden; }
[data-testid="stSidebar"] { background: #eaf2f8; }
h1, h2, h3, p { letter-spacing: 0; }

.top-shell {
    border: 1px solid var(--line);
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(236, 245, 252, 0.88));
    box-shadow: 0 18px 46px rgba(65, 93, 122, 0.16);
    padding: 10px 14px;
    margin-bottom: 8px;
}

.top-row {
    display: grid;
    grid-template-columns: minmax(280px, 1fr) repeat(3, minmax(145px, 190px));
    gap: 14px;
    align-items: stretch;
}

.brand-title {
    font-size: clamp(20px, 1.55vw, 28px);
    font-weight: 760;
    color: var(--text);
    line-height: 1.12;
}

.brand-subtitle {
    color: var(--muted);
    font-size: 13px;
    margin-top: 5px;
}

.system-status {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #315a78;
    font-size: 12px;
    margin-top: 7px;
    padding: 4px 9px;
    border: 1px solid rgba(29, 127, 184, 0.22);
    border-radius: 999px;
    background: rgba(29, 127, 184, 0.08);
}

.pulse {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: var(--green);
    box-shadow: 0 0 12px rgba(53, 211, 153, 0.9);
}

.offline-pulse {
    background: var(--red);
    box-shadow: 0 0 12px rgba(216, 77, 77, 0.65);
}

.kpi-card {
    min-height: 82px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: rgba(255, 255, 255, 0.76);
    padding: 10px 12px;
}

.kpi-label { color: var(--muted); font-size: 12px; line-height: 1.2; }
.kpi-value { color: var(--text); font-size: 26px; font-weight: 760; line-height: 1; margin-top: 9px; }
.kpi-note { color: #517999; font-size: 12px; margin-top: 7px; }

.section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 30px;
    margin-bottom: 8px;
}

.section-title { color: var(--text); font-size: 16px; font-weight: 720; }
.section-note { color: var(--muted); font-size: 12px; }

.panel {
    border: 1px solid var(--line);
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(235, 244, 251, 0.86));
    box-shadow: 0 14px 34px rgba(65, 93, 122, 0.14);
    padding: 12px;
    min-height: 100%;
}

.compact-panel {
    padding: 10px;
}

.compact-panel .section-head {
    margin-bottom: 6px;
}

.alert-list {
    max-height: 540px;
    overflow-y: auto;
    padding-right: 4px;
}

.alert-item {
    border: 1px solid rgba(132, 166, 196, 0.18);
    border-left-width: 4px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.72);
    padding: 10px 11px;
    margin-bottom: 9px;
}

.alert-item.normal { border-left-color: var(--blue); }
.alert-item.high { border-left-color: var(--amber); background: rgba(255, 246, 224, 0.86); }
.alert-item.critical { border-left-color: var(--red); background: rgba(255, 235, 235, 0.9); }

.alert-line {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    color: var(--text);
    font-size: 13px;
    font-weight: 650;
}

.alert-meta {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 8px;
    color: var(--muted);
    font-size: 12px;
    margin-top: 6px;
}

.badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    white-space: nowrap;
    border-radius: 999px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 700;
}

.badge.online { color: #ffffff; background: var(--green); }
.badge.offline { color: #536678; background: rgba(112, 132, 150, 0.18); }
.badge.normal { color: #145f8b; background: rgba(29, 127, 184, 0.12); border: 1px solid rgba(29, 127, 184, 0.2); }
.badge.high { color: #9a6418; background: rgba(199, 129, 29, 0.14); border: 1px solid rgba(199, 129, 29, 0.24); }
.badge.critical { color: #a73535; background: rgba(216, 77, 77, 0.14); border: 1px solid rgba(216, 77, 77, 0.24); }

.node-card {
    border: 1px solid rgba(132, 166, 196, 0.18);
    border-radius: 13px;
    background: rgba(255, 255, 255, 0.62);
    padding: 8px 10px;
    margin-bottom: 8px;
}

.node-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
}

.node-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.node-id { color: var(--text); font-size: 13px; font-weight: 700; overflow-wrap: anywhere; }
.node-meta {
    color: var(--muted);
    font-size: 12px;
    margin-top: 7px;
    display: grid;
    grid-template-columns: 72px 1fr;
    row-gap: 3px;
}

.control-shell {
    border-top: 1px solid var(--line);
    margin-top: 14px;
    padding-top: 12px;
}

.empty-state {
    border: 1px dashed rgba(127, 190, 255, 0.32);
    border-radius: 14px;
    min-height: 72px;
    display: grid;
    place-items: center;
    color: var(--muted);
    background: rgba(232, 242, 249, 0.62);
    font-size: 13px;
}

.runtime-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
}

.runtime-item {
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 16px;
    background: rgba(255, 255, 255, 0.62);
    color: var(--muted);
    font-size: 13px;
    overflow-wrap: anywhere;
    min-height: 82px;
}

.runtime-item b {
    display: block;
    color: var(--text);
    font-size: 15px;
    margin-bottom: 8px;
}

.settings-card {
    border: 1px solid var(--line);
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.64);
    padding: 16px;
    min-height: 150px;
}

.settings-title {
    color: var(--text);
    font-size: 16px;
    font-weight: 740;
    margin-bottom: 10px;
}

.settings-row {
    display: grid;
    grid-template-columns: 92px 1fr;
    gap: 8px;
    color: var(--muted);
    font-size: 13px;
    margin: 7px 0;
}

.settings-row span:last-child {
    color: var(--text);
    overflow-wrap: anywhere;
}

.link-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
}

.link-card {
    display: block;
    border: 1px solid rgba(29, 127, 184, 0.22);
    border-radius: 12px;
    padding: 12px;
    background: rgba(29, 127, 184, 0.08);
    color: var(--text) !important;
    text-decoration: none;
}

.link-card b {
    display: block;
    font-size: 14px;
    margin-bottom: 5px;
}

.link-card span {
    color: var(--muted);
    font-size: 12px;
    overflow-wrap: anywhere;
}

div[data-testid="stVerticalBlock"] > div:has(.panel) { height: 100%; }

.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: rgba(241, 247, 252, 0.82);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 6px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 10px;
    color: var(--muted);
    height: 38px;
    padding: 0 16px;
}

.stTabs [aria-selected="true"] {
    background: rgba(29, 127, 184, 0.12);
    color: var(--text);
}

.stTabs [data-baseweb="tab-panel"] {
    padding-top: 0.85rem;
    min-height: 520px;
}

.stButton > button {
    width: 100%;
    min-height: 40px;
    border-radius: 10px;
    border: 1px solid rgba(56, 189, 248, 0.36);
    background: linear-gradient(180deg, #2b8ec4, #1c6e9f);
    color: white;
    font-weight: 700;
}

[data-testid="stDataFrame"], [data-testid="stTable"] {
    border: 1px solid var(--line);
    border-radius: 14px;
    overflow: hidden;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid var(--line);
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(235, 244, 251, 0.86));
    box-shadow: 0 14px 34px rgba(65, 93, 122, 0.14);
    min-height: 0;
}

div[data-testid="column"] {
    padding-left: 0.25rem !important;
    padding-right: 0.25rem !important;
}

div[data-testid="stVerticalBlock"] {
    gap: 0.55rem;
}

div[data-testid="stWidgetLabel"] {
    margin-bottom: 0.15rem;
}

div[data-testid="stSlider"],
div[data-testid="stNumberInput"],
div[data-testid="stTextArea"],
div[data-testid="stSelectbox"] {
    margin-bottom: 0.15rem;
}

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
textarea,
input {
    border-radius: 10px !important;
}

@media (max-width: 1500px) {
    .alert-list { max-height: 300px; }
    .top-row { grid-template-columns: minmax(260px, 1fr) repeat(3, minmax(132px, 1fr)); }
}

@media (max-width: 980px) {
    .top-row, .runtime-grid, .node-grid { grid-template-columns: 1fr 1fr; }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_top(nodes: list[dict[str, Any]], alerts: list[dict[str, Any]]) -> None:
    today = date.today().isoformat()
    node_by_id = {item["node_id"]: item for item in nodes}
    online_count = sum(1 for node_id in DEFAULT_NODE_TYPES if node_is_online(node_by_id.get(node_id)))
    today_alerts = sum(1 for alert in alerts if str(alert.get("timestamp", "")).startswith(today))
    severe_alerts = sum(1 for alert in alerts if alert.get("level") in {"critical", "high"})
    expected = len(DEFAULT_NODE_TYPES)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    service_label, service_ok = backend_status()
    pulse_class = "pulse" if service_ok else "pulse offline-pulse"

    st.markdown(
        f"""
<div class="top-shell">
  <div class="top-row">
    <div>
      <div class="brand-title">智能车间安全监控中心</div>
      <div class="brand-subtitle">系统级 CPS 监控：视频态势、实时告警、节点心跳、远程参数下发</div>
      <div class="system-status"><span class="{pulse_class}"></span><span>{esc(service_label)} · {esc(now)}</span></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">在线节点</div>
      <div class="kpi-value">{online_count}/{expected}</div>
      <div class="kpi-note">目标节点接入状态</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">今日告警</div>
      <div class="kpi-value">{today_alerts}</div>
      <div class="kpi-note">按本地日期统计</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">高危 / 严重</div>
      <div class="kpi-value">{severe_alerts}</div>
      <div class="kpi-note">最近告警窗口</div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def build_video_tile_html(node_id: str, node_type: str, node: dict[str, Any] | None, alerts: list[dict[str, Any]]) -> str:
    stream_url = f"http://localhost:{ServerConfig().mjpeg_port}/stream?node_id={node_id}"
    status = "online" if node_is_online(node) else "offline"
    status_label = "在线" if status == "online" else "离线"
    alert_count = sum(1 for alert in alerts if alert.get("node_id") == node_id)
    fallback = latest_frame_path(node_id)
    frame_age = frame_age_seconds(node_id)
    frame_label = "无视频帧" if frame_age is None else ("刚更新" if frame_age < 2 else f"{int(frame_age)}秒前")
    heartbeat_label = short_time(node.get("last_seen")) if node else "-"
    placeholder_text = "等待视频流接入"
    if fallback and fallback.exists():
        placeholder_text = f"检测到最近帧：{fallback.name}"

    return f"""
<div class="tile">
    <div class="bar">
      <div class="title">{esc(NODE_LABELS.get(node_type, node_type))}<span class="sub">{esc(node_id)}</span></div>
      <span class="badge {esc(status)}">{esc(status_label)}</span>
    </div>
    <div class="stage">
      <div class="placeholder">{esc(placeholder_text)}</div>
      <img src="{esc(stream_url)}" alt="{esc(node_id)} video stream" />
    </div>
    <div class="bar bottom">
      <span class="metric">心跳 {esc(heartbeat_label)}</span>
      <span class="metric">视频 {esc(frame_label)}</span>
      <span class="metric">{esc(NODE_PORTS.get(node_id, "-"))}</span>
      <span class="metric">告警 {alert_count}</span>
    </div>
  </div>
"""


def render_video_panel(nodes: list[dict[str, Any]], alerts: list[dict[str, Any]]) -> None:
    node_by_id = {item["node_id"]: item for item in nodes}
    video_nodes = list(DEFAULT_NODE_TYPES.keys())
    known_node_ids = [item["node_id"] for item in nodes if item["node_id"] not in video_nodes]
    video_nodes.extend(known_node_ids[: max(0, 4 - len(video_nodes))])
    tiles = "\n".join(
        build_video_tile_html(node_id, DEFAULT_NODE_TYPES.get(node_id, "unknown"), node_by_id.get(node_id), alerts)
        for node_id in video_nodes[:4]
    )

    components.html(
        f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
html, body {{
    margin: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    font-family: "Inter", "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    background: transparent;
    color: #13283d;
}}
.panel {{
    height: 100%;
    box-sizing: border-box;
    border: 1px solid rgba(77, 116, 154, 0.18);
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(235, 244, 251, 0.86));
    box-shadow: 0 14px 34px rgba(65, 93, 122, 0.14);
    padding: 14px;
}}
.section-head {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 34px;
    margin-bottom: 10px;
}}
.section-title {{ font-size: 16px; font-weight: 720; }}
.section-note {{ color: #60768b; font-size: 12px; }}
.grid {{
    height: calc(100% - 44px);
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-template-rows: repeat(2, minmax(0, 1fr));
    gap: 10px;
}}
.tile {{
    min-height: 0;
    box-sizing: border-box;
    border: 1px solid rgba(77, 116, 154, 0.2);
    border-radius: 14px;
    overflow: hidden;
    background: linear-gradient(180deg, rgba(250, 253, 255, 0.98), rgba(232, 242, 249, 0.98));
    display: grid;
    grid-template-rows: 38px minmax(0, 1fr) 34px;
}}
.bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 0 10px;
    background: rgba(231, 241, 249, 0.9);
    border-bottom: 1px solid rgba(77, 116, 154, 0.16);
    font-size: 11.5px;
}}
.bottom {{
    border-top: 1px solid rgba(77, 116, 154, 0.16);
    border-bottom: 0;
    color: #60768b;
}}
.title {{
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 700;
}}
.sub {{ color: #60768b; font-weight: 500; margin-left: 6px; }}
.badge {{
    flex: 0 0 auto;
    border-radius: 999px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 800;
}}
.online {{ color: #ffffff; background: #1f9d72; }}
.offline {{ color: #536678; background: rgba(112, 132, 150, 0.18); }}
.stage {{
    position: relative;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background:
        linear-gradient(rgba(68, 124, 166, 0.1) 1px, transparent 1px),
        linear-gradient(90deg, rgba(68, 124, 166, 0.1) 1px, transparent 1px),
        #eef5fa;
    background-size: 28px 28px;
}}
.stage img {{
    display: block;
    max-width: 100%;
    max-height: 100%;
    width: 100%;
    height: 100%;
    object-fit: contain;
    object-position: center center;
    position: relative;
    z-index: 1;
}}
.placeholder {{
    position: absolute;
    inset: 14px;
    border: 1px dashed rgba(77, 116, 154, 0.26);
    border-radius: 12px;
    display: grid;
    place-items: center;
    color: #60768b;
    font-size: 12px;
    text-align: center;
    padding: 12px;
    box-sizing: border-box;
    z-index: 0;
}}
.metric {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
</style>
</head>
<body>
  <div class="panel">
    <div class="section-head">
      <div class="section-title">四路视频监控</div>
      <div class="section-note">MJPEG 实时流 · 画面自适应居中</div>
    </div>
    <div class="grid">{tiles}</div>
  </div>
</body>
</html>
        """,
        height=980,
        scrolling=False,
    )


def render_alerts(alerts: list[dict[str, Any]]) -> None:
    items = []
    for alert in alerts:
        level = str(alert.get("level", "normal"))
        label, cls = LEVEL_META.get(level, (level, "normal"))
        confidence = float(alert.get("confidence", 0.0) or 0.0)
        items.append(
            f"""
<div class="alert-item {esc(cls)}">
  <div class="alert-line">
    <span>{esc(alert.get("alert_type", "unknown"))}</span>
    <span class="badge {esc(cls)}">{esc(label)}</span>
  </div>
  <div class="alert-meta">
    <span>{esc(short_time(alert.get("timestamp")))} · {esc(alert.get("node_id", "-"))}</span>
    <span>置信度 {confidence:.2f}</span>
  </div>
</div>
            """
        )
    content = "\n".join(items) if items else '<div class="empty-state">暂无实时告警</div>'
    st.markdown(
        f"""
<div class="panel">
  <div class="section-head">
    <div class="section-title">实时告警</div>
    <div class="section-note">最新在上</div>
  </div>
  <div class="alert-list">{content}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_alerts_compact(alerts: list[dict[str, Any]]) -> None:
    items = []
    for alert in alerts[:12]:
        level = str(alert.get("level", "normal"))
        label, cls = LEVEL_META.get(level, (level, "normal"))
        confidence = float(alert.get("confidence", 0.0) or 0.0)
        items.append(
            f"""
<div class="alert-item {esc(cls)}">
  <div class="alert-line">
    <span>{esc(alert.get("alert_type", "unknown"))}</span>
    <span class="badge {esc(cls)}">{esc(label)}</span>
  </div>
  <div class="alert-meta">
    <span>{esc(short_time(alert.get("timestamp")))} · {esc(alert.get("node_id", "-"))}</span>
    <span>置信度 {confidence:.2f}</span>
  </div>
</div>
            """
        )
    content = "\n".join(items) if items else '<div class="empty-state">暂无实时告警</div>'
    st.markdown(
        f"""
<div class="panel compact-panel">
  <div class="section-head">
    <div class="section-title">实时告警</div>
    <div class="section-note">最新在上</div>
  </div>
  <div class="alert-list">{content}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_node_cards(nodes: list[dict[str, Any]]) -> None:
    node_by_id = {item["node_id"]: item for item in nodes}
    cards = []
    for node_id, default_type in DEFAULT_NODE_TYPES.items():
        node = node_by_id.get(node_id)
        status = "online" if node_is_online(node) else "offline"
        node_type = str(node.get("node_type", default_type)) if node else default_type
        last_seen = str(node.get("last_seen", "-")) if node else "-"
        cards.append(
            f"""
<div class="node-card">
  <div class="node-top">
    <div class="node-id">{esc(node_id)}</div>
    <span class="badge {esc(status)}">{'在线' if status == 'online' else '离线'}</span>
  </div>
  <div class="node-meta">
    <span>类型</span><span>{esc(NODE_LABELS.get(node_type, node_type))}</span>
    <span>心跳</span><span>{esc(short_time(last_seen))}</span>
  </div>
</div>
            """
        )

    st.markdown(
        f"""
<div class="section-head">
  <div class="section-title">节点状态</div>
  <div class="section-note">4 个单元级 CPS</div>
</div>
{''.join(cards)}
        """,
        unsafe_allow_html=True,
    )


def render_nodes_panel(nodes: list[dict[str, Any]]) -> None:
    node_by_id = {item["node_id"]: item for item in nodes}
    cards = []
    for node_id, default_type in DEFAULT_NODE_TYPES.items():
        node = node_by_id.get(node_id)
        status = "online" if node_is_online(node) else "offline"
        node_type = str(node.get("node_type", default_type)) if node else default_type
        last_seen = str(node.get("last_seen", "-")) if node else "-"
        video_age = frame_age_seconds(node_id)
        video_label = "无视频帧" if video_age is None else ("刚更新" if video_age < 2 else f"{int(video_age)}秒前")
        cards.append(
            f"""
<div class="node-card">
  <div class="node-top">
    <div class="node-id">{esc(node_id)}</div>
    <span class="badge {esc(status)}">{'在线' if status == 'online' else '离线'}</span>
  </div>
  <div class="node-meta">
    <span>类型</span><span>{esc(NODE_LABELS.get(node_type, node_type))}</span>
    <span>心跳</span><span>{esc(short_time(last_seen))}</span>
    <span>视频</span><span>{esc(video_label)}</span>
  </div>
</div>
            """
        )
    st.markdown(
        f"""
<div class="panel">
  <div class="section-head">
    <div class="section-title">节点状态</div>
    <div class="section-note">4 个单元级 CPS</div>
  </div>
  <div class="node-grid">{''.join(cards)}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_right_panel(nodes: list[dict[str, Any]]) -> None:
    node_options = sorted(set(list(DEFAULT_NODE_TYPES.keys()) + [item["node_id"] for item in nodes]))
    with st.container(border=False):
        st.markdown('<div class="section-title">远程控制</div>', unsafe_allow_html=True)

    target_node = st.selectbox("目标节点", node_options, key="target_node")
    confidence = st.slider("置信度阈值", min_value=0.05, max_value=0.95, value=0.5, step=0.05, key="confidence")
    cooldown = st.number_input("告警冷却时间（秒）", min_value=1, max_value=600, value=30, key="cooldown")
    extra_json = st.text_area("附加 JSON 配置", value="{}", height=88, key="extra_json")

    if st.button("下发配置", type="primary", use_container_width=True):
        try:
            extra = json.loads(extra_json) if extra_json.strip() else {}
            payload = {
                "command": "update_config",
                "target_node": target_node,
                "config": {
                    "confidence_threshold": confidence,
                    "alert_cooldown_seconds": int(cooldown),
                    **extra,
                },
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
        except json.JSONDecodeError as exc:
            st.error(f"附加 JSON 格式错误：{exc}")
        else:
            if send_control_command(target_node, payload):
                st.success("控制命令已发送")
            else:
                st.error("发送失败，请确认后端服务正在运行")


def render_bottom_tabs(db: Database, nodes: list[dict[str, Any]]) -> None:
    node_by_id = {item["node_id"]: item for item in nodes}
    tab_logs, tab_stats, tab_settings = st.tabs(["日志查询", "统计图表", "系统设置"])

    with tab_logs:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            start = st.date_input("开始日期", value=date.today())
        with col2:
            end = st.date_input("结束日期", value=date.today())
        with col3:
            selected_node = st.selectbox("节点", [""] + sorted(node_by_id.keys()), key="log_node")
        with col4:
            selected_type = st.text_input("告警类型")

        queried = db.query_alerts(
            start_date=datetime.combine(start, dt_time.min).isoformat(timespec="seconds"),
            end_date=datetime.combine(end, dt_time.max).isoformat(timespec="seconds"),
            node_id=selected_node or None,
            alert_type=selected_type or None,
            limit=500,
        )
        st.dataframe(queried, use_container_width=True, hide_index=True, height=430)

    with tab_stats:
        stats = db.list_statistics(days=30)
        if stats:
            chart_col, table_col = st.columns([1.75, 1], gap="medium")
            with chart_col:
                st.bar_chart(stats, x="date", y="count", color="alert_type", height=430)
            with table_col:
                st.dataframe(stats, use_container_width=True, hide_index=True, height=430)
        else:
            st.markdown('<div class="empty-state">暂无统计数据</div>', unsafe_allow_html=True)

    with tab_settings:
        app_url = "http://localhost:8501"
        mjpeg_base = f"http://localhost:{ServerConfig().mjpeg_port}/stream"
        service_label, _ = backend_status()
        node_by_id = {item["node_id"]: item for item in nodes}
        online_count = sum(1 for node_id in DEFAULT_NODE_TYPES if node_is_online(node_by_id.get(node_id)))
        st.markdown(
            f"""
<div class="runtime-grid">
  <div class="settings-card">
    <div class="settings-title">运行信息</div>
    <div class="settings-row"><span>服务状态</span><span>{esc(service_label)}</span></div>
    <div class="settings-row"><span>在线节点</span><span>{online_count}/{len(DEFAULT_NODE_TYPES)}</span></div>
    <div class="settings-row"><span>数据库</span><span>{esc(DB_PATH)}</span></div>
    <div class="settings-row"><span>TCP 端口</span><span>{esc(ServerConfig().tcp_ports)}</span></div>
    <div class="settings-row"><span>UDP 端口</span><span>{esc(ServerConfig().udp_ports)}</span></div>
    <div class="settings-row"><span>视频端口</span><span>{esc(ServerConfig().mjpeg_port)}</span></div>
  </div>
  <div class="settings-card">
    <div class="settings-title">常用入口</div>
    <div class="link-grid">
      <a class="link-card" href="{esc(app_url)}" target="_blank"><b>监控中心</b><span>{esc(app_url)}</span></a>
      <a class="link-card" href="{esc(mjpeg_base)}?node_id=smoking-001" target="_blank"><b>吸烟视频流</b><span>smoking-001</span></a>
      <a class="link-card" href="{esc(mjpeg_base)}?node_id=fire-smoke-001" target="_blank"><b>火焰烟雾流</b><span>fire-smoke-001</span></a>
      <a class="link-card" href="{esc(mjpeg_base)}?node_id=helmet-001" target="_blank"><b>安全帽视频流</b><span>helmet-001</span></a>
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="settings-title">刷新行为</div>', unsafe_allow_html=True)
        setting_left, setting_right, setting_action = st.columns([1.25, 0.75, 1], gap="medium")
        with setting_left:
            refresh = st.slider("自动刷新间隔（秒）", 1, 30, 2)
        with setting_right:
            auto_refresh = st.checkbox("自动刷新", value=True)
        with setting_action:
            if st.button("立即刷新页面", use_container_width=True):
                st.rerun()
        if auto_refresh:
            if hasattr(st, "autorefresh"):
                st.autorefresh(interval=refresh * 1000, key="monitor_center_refresh")
            else:
                st.caption("当前 Streamlit 版本不支持 st.autorefresh，请手动刷新页面。")


def main() -> None:
    inject_css()
    db = get_database()
    nodes = db.list_nodes()
    alerts = db.list_alerts(limit=80)

    render_top(nodes, alerts)

    left, right = st.columns([7, 3], gap="medium")
    with left:
        render_video_panel(nodes, alerts)
        st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)
        render_nodes_panel(nodes)
    with right:
        with st.container(border=True):
            st.markdown('<div class="section-head"><div class="section-title">运维控制台</div><div class="section-note">状态 + 参数</div></div>', unsafe_allow_html=True)
            render_alerts_compact(alerts)
            st.markdown("<div style='height: 2px'></div>", unsafe_allow_html=True)
            render_right_panel(nodes)

    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
    render_bottom_tabs(db, nodes)


if __name__ == "__main__":
    main()
