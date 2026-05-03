"""Single-unit CPS dashboard for smoke detection."""

from __future__ import annotations

import html
import json
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DB_PATH, ServerConfig, ensure_data_dirs  # noqa: E402
from database import Database  # noqa: E402
from protocol_parser import MessageType, encode_frame  # noqa: E402


NODE_ID = "fire-smoke-001"
MJPEG_URL = f"http://localhost:{ServerConfig().mjpeg_port}/stream?node_id={NODE_ID}"


st.set_page_config(
    page_title="烟雾检测单元级 CPS",
    page_icon="SMK",
    layout="wide",
    initial_sidebar_state="collapsed",
)
ensure_data_dirs()


@st.cache_resource
def get_database() -> Database:
    return Database(DB_PATH)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def short_time(value: object) -> str:
    parsed = parse_time(value)
    return parsed.strftime("%H:%M:%S") if parsed else "-"


def node_is_online(node: dict[str, Any] | None, stale_seconds: int = 30) -> bool:
    if not node or node.get("status") != "online":
        return False
    last_seen = parse_time(node.get("last_seen"))
    return bool(last_seen and (datetime.now() - last_seen).total_seconds() <= stale_seconds)


def smoke_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    smoke_types = {"smoke", "smoke_alarm", "fire"}
    return [
        item
        for item in alerts
        if item.get("node_id") == NODE_ID and str(item.get("alert_type", "")).lower() in smoke_types
    ]


def parse_sensor_fields(alert: dict[str, Any] | None) -> dict[str, float]:
    if not alert:
        return {}
    description = str(alert.get("description", ""))
    data: dict[str, float] = {}
    for key in ("simulated_sensor", "adc", "fused", "video", "avg", "threshold"):
        marker = f"{key}="
        if marker not in description:
            continue
        tail = description.split(marker, 1)[1]
        raw = tail.split(",", 1)[0].split(" ", 1)[0].replace("ppm", "")
        try:
            data[key] = float(raw)
        except ValueError:
            continue
    return data


def sensor_rows(alerts: list[dict[str, Any]], limit: int = 18) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for alert in reversed(alerts[:limit]):
        sensor = parse_sensor_fields(alert)
        if not sensor:
            continue
        rows.append(
            {
                "time": short_time(alert.get("timestamp")),
                "ppm": sensor.get("simulated_sensor", 0.0),
                "adc": sensor.get("adc", 0.0),
                "fused": sensor.get("fused", float(alert.get("confidence", 0.0) or 0.0)),
                "threshold": sensor.get("threshold", 300.0),
            }
        )
    return rows


def send_control(payload: dict[str, Any]) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", ServerConfig().tcp_ports[0]), timeout=2.0) as sock:
            sock.sendall(encode_frame(MessageType.REGISTER, "smoke-ui", {"node_type": "smoke_unit_ui"}))
            sock.sendall(encode_frame(MessageType.CONTROL, "monitor-center", payload))
        return True
    except OSError:
        return False


def inject_css() -> None:
    st.markdown(
        """
<style>
:root {
    --bg: #eef3f7;
    --panel: #ffffff;
    --panel-2: #f8fbfd;
    --line: #d4e0e8;
    --text: #142435;
    --muted: #667887;
    --green: #16815f;
    --blue: #176d9c;
    --amber: #b97216;
    --red: #c93d3d;
}

.stApp { background: var(--bg); color: var(--text); }
.block-container { max-width: 1500px; padding: 14px 18px 24px; }
#MainMenu, footer, header { visibility: hidden; }

.page-head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    padding: 12px 14px;
    margin-bottom: 10px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
}
.title { font-size: 27px; font-weight: 760; line-height: 1.15; }
.subtitle { margin-top: 5px; color: var(--muted); font-size: 14px; }
.status-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 7px 11px;
    background: var(--panel-2);
    font-size: 13px;
    white-space: nowrap;
}
.dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.dot.ok { background: var(--green); }
.dot.bad { background: var(--red); }

.metric-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(140px, 1fr));
    gap: 10px;
    margin-bottom: 12px;
}
.metric {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 11px 12px;
}
.metric-label { color: var(--muted); font-size: 12px; }
.metric-value { font-size: 25px; font-weight: 760; margin-top: 5px; }
.metric-note { color: var(--muted); font-size: 12px; margin-top: 3px; min-height: 16px; }
.metric.danger { border-left: 4px solid var(--red); }
.metric.ok { border-left: 4px solid var(--green); }

.panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 12px;
}
.section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
}
.section-title { font-size: 17px; font-weight: 730; }
.section-note { color: var(--muted); font-size: 12px; }
.video-frame {
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #101820;
    border: 1px solid #0d1720;
    border-radius: 6px;
    overflow: hidden;
}
.video-frame img { width: 100%; height: 100%; object-fit: contain; display: block; }

.gauge-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 10px;
}
.gauge {
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px 11px;
    background: var(--panel-2);
}
.gauge-top { display: flex; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 12px; }
.gauge-value { margin-top: 6px; font-size: 23px; font-weight: 760; }
.bar { height: 8px; border-radius: 999px; background: #e5edf3; overflow: hidden; margin-top: 8px; }
.bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--green), var(--amber), var(--red)); }

.trend-chart {
    width: 100%;
    height: 280px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--panel-2);
}
.chart-axis { stroke: #c5d3dd; stroke-width: 1; }
.chart-grid { stroke: #e3ebf0; stroke-width: 1; }
.chart-threshold { stroke: var(--red); stroke-width: 1.5; stroke-dasharray: 5 5; }
.chart-ppm { fill: none; stroke: var(--amber); stroke-width: 2.6; }
.chart-adc { fill: none; stroke: var(--blue); stroke-width: 2; opacity: .72; }
.chart-dot { fill: var(--amber); stroke: #fff; stroke-width: 1.5; }
.chart-label { fill: var(--muted); font-size: 11px; }

.alert-list { display: grid; gap: 8px; max-height: 390px; overflow: auto; }
.alert-item {
    border: 1px solid var(--line);
    border-left: 4px solid var(--amber);
    border-radius: 7px;
    padding: 9px 10px;
    background: var(--panel-2);
}
.alert-line { display: flex; justify-content: space-between; gap: 10px; font-weight: 700; }
.alert-meta, .alert-desc { color: var(--muted); font-size: 12px; margin-top: 4px; }
.empty { color: var(--muted); padding: 14px 0; }

@media (max-width: 1100px) {
    .metric-grid, .gauge-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
    .page-head { display: block; }
    .status-chip { margin-top: 10px; }
    .metric-grid, .gauge-grid { grid-template-columns: 1fr; }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_header(node: dict[str, Any] | None) -> None:
    online = node_is_online(node)
    status_text = "在线" if online else "离线"
    dot_class = "ok" if online else "bad"
    last_seen = node.get("last_seen", "-") if node else "-"
    st.markdown(
        f"""
<div class="page-head">
  <div>
    <div class="title">烟雾检测单元级 CPS</div>
    <div class="subtitle">视频识别、模拟烟雾传感器数据、融合报警和参数下发集中在一个单元操作台</div>
  </div>
  <div class="status-chip"><span class="dot {dot_class}"></span>{status_text} · {esc(NODE_ID)} · {esc(last_seen)}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(node: dict[str, Any] | None, alerts: list[dict[str, Any]]) -> None:
    latest = alerts[0] if alerts else None
    sensor = parse_sensor_fields(latest)
    ppm = sensor.get("simulated_sensor", 0.0)
    adc = sensor.get("adc", 0.0)
    fused = sensor.get("fused", float(latest.get("confidence", 0.0) or 0.0) if latest else 0.0)
    threshold = sensor.get("threshold", 300.0)
    latest_type = latest.get("alert_type", "无") if latest else "无"
    online_class = "ok" if node_is_online(node) else "danger"
    alarm_class = "danger" if ppm >= threshold and latest else "ok"
    st.markdown(
        f"""
<div class="metric-grid">
  <div class="metric {online_class}">
    <div class="metric-label">节点状态</div>
    <div class="metric-value">{"在线" if node_is_online(node) else "离线"}</div>
    <div class="metric-note">TCP 5001 / UDP 5000</div>
  </div>
  <div class="metric {alarm_class}">
    <div class="metric-label">当前 ppm</div>
    <div class="metric-value">{ppm:.0f}</div>
    <div class="metric-note">阈值 {threshold:.0f} ppm</div>
  </div>
  <div class="metric">
    <div class="metric-label">ADC 原始值</div>
    <div class="metric-value">{adc:.0f}</div>
    <div class="metric-note">0-1023 模拟读数</div>
  </div>
  <div class="metric">
    <div class="metric-label">融合置信度</div>
    <div class="metric-value">{fused:.2f}</div>
    <div class="metric-note">视频 + 传感器</div>
  </div>
  <div class="metric">
    <div class="metric-label">最近事件</div>
    <div class="metric-value">{esc(latest_type)}</div>
    <div class="metric-note">{esc(short_time(latest.get("timestamp") if latest else None))}</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_video_panel() -> None:
    st.markdown(
        f"""
<div class="panel">
  <div class="section-head">
    <div class="section-title">实时烟雾视频</div>
    <div class="section-note">{esc(MJPEG_URL)}</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )
    components.html(
        f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ margin: 0; background: transparent; }}
.video-frame {{
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #101820;
  border: 1px solid #0d1720;
  border-radius: 6px;
  overflow: hidden;
}}
.video-frame img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
</style>
</head>
<body>
  <div class="video-frame"><img src="{esc(MJPEG_URL)}" alt="smoke unit video"></div>
</body>
</html>
        """,
        height=610,
    )


def render_gauge(title: str, value: float, unit: str, note: str, percent: float) -> str:
    pct = min(100.0, max(0.0, percent))
    return f"""
<div class="gauge">
  <div class="gauge-top"><span>{esc(title)}</span><span>{esc(note)}</span></div>
  <div class="gauge-value">{value:.2f}{esc(unit)}</div>
  <div class="bar"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>
</div>
    """


def render_sensor_panel(alerts: list[dict[str, Any]]) -> None:
    rows = sensor_rows(alerts)
    latest = rows[-1] if rows else {"ppm": 0.0, "adc": 0.0, "fused": 0.0, "threshold": 300.0}
    max_ppm = max(latest["threshold"] * 1.25, *(row["ppm"] for row in rows), 1.0) if rows else 375.0
    gauges = "".join(
        [
            render_gauge("烟雾浓度", latest["ppm"], " ppm", f"阈值 {latest['threshold']:.0f}", latest["ppm"] / max_ppm * 100.0),
            render_gauge("ADC", latest["adc"], "", "0-1023", latest["adc"] / 1023.0 * 100.0),
            render_gauge("融合置信度", latest["fused"], "", "0-1", latest["fused"] * 100.0),
        ]
    )
    st.markdown(
        f"""
<div class="panel">
  <div class="section-head">
    <div class="section-title">传感器融合状态</div>
    <div class="section-note">最近 {len(rows)} 条烟雾报警记录</div>
  </div>
  <div class="gauge-grid">{gauges}</div>
        """,
        unsafe_allow_html=True,
    )
    render_trend_chart(rows)
    st.markdown("</div>", unsafe_allow_html=True)


def render_trend_chart(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.markdown('<div class="empty">暂无可显示的传感器曲线</div>', unsafe_allow_html=True)
        return

    threshold = rows[-1].get("threshold", 300.0)
    max_ppm = max(threshold * 1.25, *(row["ppm"] for row in rows), 1.0)
    max_adc = max(1023.0, *(row["adc"] for row in rows))
    width, height = 760, 280
    left, right, top, bottom = 46, 18, 18, 34
    chart_w, chart_h = width - left - right, height - top - bottom
    count = max(1, len(rows) - 1)

    def point(index: int, value: float, max_value: float) -> tuple[float, float]:
        x = left + chart_w * index / count
        y = top + chart_h * (1.0 - min(1.0, max(0.0, value / max_value)))
        return x, y

    ppm_points = [point(index, row["ppm"], max_ppm) for index, row in enumerate(rows)]
    adc_points = [point(index, row["adc"], max_adc) for index, row in enumerate(rows)]
    threshold_y = point(0, threshold, max_ppm)[1]
    ppm_path = " ".join(f"{x:.1f},{y:.1f}" for x, y in ppm_points)
    adc_path = " ".join(f"{x:.1f},{y:.1f}" for x, y in adc_points)
    dots = "\n".join(f'<circle class="chart-dot" cx="{x:.1f}" cy="{y:.1f}" r="3" />' for x, y in ppm_points)
    grid_lines = "\n".join(
        f'<line class="chart-grid" x1="{left}" y1="{top + chart_h * i / 4:.1f}" x2="{width - right}" y2="{top + chart_h * i / 4:.1f}" />'
        for i in range(1, 4)
    )
    st.markdown(
        f"""
<svg class="trend-chart" viewBox="0 0 {width} {height}" role="img" aria-label="smoke sensor trend">
  {grid_lines}
  <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" />
  <line class="chart-axis" x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" />
  <line class="chart-threshold" x1="{left}" y1="{threshold_y:.1f}" x2="{width - right}" y2="{threshold_y:.1f}" />
  <polyline class="chart-adc" points="{adc_path}" />
  <polyline class="chart-ppm" points="{ppm_path}" />
  {dots}
  <text class="chart-label" x="{left}" y="{height - 12}">{esc(rows[0]["time"])}</text>
  <text class="chart-label" x="{width - right - 58}" y="{height - 12}">{esc(rows[-1]["time"])}</text>
  <text class="chart-label" x="{left + 8}" y="{max(12, threshold_y - 7):.1f}">阈值 {threshold:.0f} ppm</text>
  <text class="chart-label" x="{width - right - 132}" y="{top + 14}">ppm 黄线 · ADC 蓝线</text>
</svg>
        """,
        unsafe_allow_html=True,
    )


def render_alerts(alerts: list[dict[str, Any]]) -> None:
    if not alerts:
        st.markdown('<div class="empty">暂无烟雾报警记录</div>', unsafe_allow_html=True)
        return

    items = []
    for alert in alerts[:18]:
        confidence = float(alert.get("confidence", 0.0) or 0.0)
        sensor = parse_sensor_fields(alert)
        sensor_text = ""
        if sensor:
            sensor_text = f'<br>ppm={sensor.get("simulated_sensor", 0.0):.0f} · adc={sensor.get("adc", 0.0):.0f} · fused={sensor.get("fused", confidence):.2f}'
        items.append(
            f"""
<div class="alert-item">
  <div class="alert-line">
    <span>{esc(alert.get("alert_type", "unknown"))}</span>
    <span>{confidence:.2f}</span>
  </div>
  <div class="alert-meta">{esc(short_time(alert.get("timestamp")))} · {esc(alert.get("level", "normal"))}</div>
  <div class="alert-desc">{esc(alert.get("description", ""))}{sensor_text}</div>
</div>
            """
        )
    st.markdown(f'<div class="alert-list">{"".join(items)}</div>', unsafe_allow_html=True)


def render_control_panel() -> None:
    st.markdown('<div class="section-title">参数下发</div>', unsafe_allow_html=True)
    with st.form("smoke_control"):
        confidence = st.slider("视频置信度阈值", 0.05, 0.95, 0.35, 0.05)
        cooldown = st.number_input("报警冷却时间（秒）", min_value=1, max_value=600, value=3)
        alarm_ppm = st.number_input("烟雾传感器报警阈值（ppm）", min_value=50, max_value=2000, value=300, step=10)
        min_hits = st.number_input("窗口内最小命中帧数", min_value=1, max_value=10, value=2)
        extra = st.text_area("附加 JSON 配置", value="{}", height=78)
        submitted = st.form_submit_button("下发到烟雾单元")

    if not submitted:
        return

    try:
        extra_config = json.loads(extra) if extra.strip() else {}
    except json.JSONDecodeError as exc:
        st.error(f"附加 JSON 格式错误：{exc}")
        return

    payload = {
        "target_node_id": NODE_ID,
        "command": "update_config",
        "config": {
            "alert_conf_threshold": float(confidence),
            "alert_cooldown_seconds": int(cooldown),
            "smoke_sensor_alarm_ppm": float(alarm_ppm),
            "smoke_alarm_min_hits": int(min_hits),
            **extra_config,
        },
    }
    if send_control(payload):
        st.success("参数已下发")
    else:
        st.error("后端未连接，无法下发参数")


def main() -> None:
    inject_css()
    db = get_database()
    nodes = db.list_nodes()
    node = next((item for item in nodes if item.get("node_id") == NODE_ID), None)
    alerts = smoke_alerts(db.list_alerts(limit=160))

    render_header(node)
    render_metrics(node, alerts)

    video_col, side_col = st.columns([1.75, 1.0], gap="medium")
    with video_col:
        render_video_panel()
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        render_sensor_panel(alerts)

    with side_col:
        st.markdown('<div class="panel"><div class="section-head"><div class="section-title">报警记录</div><div class="section-note">最近事件</div></div>', unsafe_allow_html=True)
        render_alerts(alerts)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        render_control_panel()
        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
