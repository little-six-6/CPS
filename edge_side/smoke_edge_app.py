"""Local single-unit CPS dashboard for the smoke edge node."""

from __future__ import annotations

import html
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.fire_config import ALERT_CONFIG, CAMERA_CONFIG, MODEL_CONFIG, NETWORK_CONFIG  # noqa: E402
from core.pipeline import EdgePipeline  # noqa: E402

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


st.set_page_config(
    page_title="烟雾检测边缘单元 CPS",
    page_icon="SMK",
    layout="wide",
    initial_sidebar_state="collapsed",
)


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
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value)).strftime("%H:%M:%S")
        except (OSError, ValueError):
            return "-"
    parsed = parse_time(value)
    return parsed.strftime("%H:%M:%S") if parsed else "-"


def parse_sensor_fields(description: object) -> dict[str, float]:
    text = str(description or "")
    data: dict[str, float] = {}
    for key in ("simulated_sensor", "adc", "fused", "video", "avg", "threshold"):
        marker = f"{key}="
        if marker not in text:
            continue
        tail = text.split(marker, 1)[1]
        raw = tail.split(",", 1)[0].split(" ", 1)[0].replace("ppm", "")
        try:
            data[key] = float(raw)
        except ValueError:
            continue
    return data


def frame_for_streamlit(frame: Any) -> Any:
    if frame is None:
        return None
    if cv2 is None:
        return frame
    try:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    except Exception:
        return frame


def ensure_pipeline() -> EdgePipeline:
    pipeline = st.session_state.get("edge_pipeline", None)
    if pipeline is None:
        pipeline = EdgePipeline(
            camera_config=CAMERA_CONFIG,
            model_config=MODEL_CONFIG,
            alert_config=ALERT_CONFIG,
            network_config=NETWORK_CONFIG,
        )
        st.session_state.edge_pipeline = pipeline
        st.session_state.edge_running = False
        st.session_state.sensor_history = []
        st.session_state.alert_history = []
    return pipeline


def start_monitoring() -> None:
    pipeline = ensure_pipeline()
    if not st.session_state.get("edge_running"):
        pipeline.start()
        st.session_state.edge_running = True


def stop_monitoring() -> None:
    pipeline = st.session_state.get("edge_pipeline")
    if pipeline is not None:
        pipeline.stop()
    st.session_state.edge_running = False


def step_pipeline() -> None:
    pipeline = st.session_state.get("edge_pipeline")
    if pipeline is None:
        return
    try:
        pipeline.step()
        st.session_state.last_error = ""
        st.session_state.last_update = time.time()
    except Exception as exc:
        st.session_state.last_error = str(exc)
        st.session_state.edge_running = False


def get_current_state() -> dict[str, Any]:
    pipeline = ensure_pipeline()
    last_alert = pipeline.last_alert_packet
    sensor = parse_sensor_fields(last_alert.description if last_alert else "")
    if last_alert and sensor:
        history = st.session_state.setdefault("sensor_history", [])
        history.append(
            {
                "time": short_time(last_alert.timestamp),
                "ppm": sensor.get("simulated_sensor", 0.0),
                "adc": sensor.get("adc", 0.0),
                "fused": sensor.get("fused", float(last_alert.confidence)),
                "threshold": sensor.get("threshold", ALERT_CONFIG.smoke_sensor_alarm_ppm),
            }
        )
        st.session_state.sensor_history = history[-30:]
        alerts = st.session_state.setdefault("alert_history", [])
        if not alerts or alerts[-1].get("id") != last_alert.alert_id:
            alerts.append(
                {
                    "id": last_alert.alert_id,
                    "time": short_time(last_alert.timestamp),
                    "type": last_alert.alert_type,
                    "level": last_alert.alert_level,
                    "confidence": last_alert.confidence,
                    "description": last_alert.description,
                    "sensor": sensor,
                }
            )
            st.session_state.alert_history = alerts[-20:]
    return {
        "running": bool(st.session_state.get("edge_running")),
        "pipeline": pipeline,
        "last_frame": pipeline.last_frame,
        "last_inference": pipeline.last_inference,
        "last_alert": last_alert,
        "sensor": sensor,
        "stats": pipeline.stats,
    }


def inject_css() -> None:
    st.markdown(
        """
<style>
:root {
  --bg: #eef3f7;
  --panel: #ffffff;
  --panel-2: #f8fbfd;
  --line: #d5e0e8;
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
.page-head, .panel, .metric, .control, .item {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 14px;
  padding: 12px 14px;
  margin-bottom: 10px;
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
.metric-grid { display: grid; grid-template-columns: repeat(5, minmax(140px, 1fr)); gap: 10px; margin-bottom: 12px; }
.metric { padding: 11px 12px; }
.metric-label { color: var(--muted); font-size: 12px; }
.metric-value { font-size: 25px; font-weight: 760; margin-top: 5px; }
.metric-note { color: var(--muted); font-size: 12px; margin-top: 3px; min-height: 16px; }
.metric.danger { border-left: 4px solid var(--red); }
.metric.ok { border-left: 4px solid var(--green); }
.layout { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(340px, 0.9fr); gap: 12px; }
.panel { padding: 12px; }
.section-head { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 10px; align-items: center; }
.section-title { font-size: 17px; font-weight: 730; }
.section-note { color: var(--muted); font-size: 12px; }
.video-frame { width: 100%; aspect-ratio: 16 / 9; background: #101820; border: 1px solid #0d1720; border-radius: 6px; overflow: hidden; }
.video-frame img { width: 100%; height: 100%; object-fit: contain; display: block; }
.gauge-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 10px; }
.gauge { border: 1px solid var(--line); border-radius: 8px; padding: 10px 11px; background: var(--panel-2); }
.gauge-top { display: flex; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 12px; }
.gauge-value { margin-top: 6px; font-size: 23px; font-weight: 760; }
.bar { height: 8px; border-radius: 999px; background: #e5edf3; overflow: hidden; margin-top: 8px; }
.bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--green), var(--amber), var(--red)); }
.trend-chart { width: 100%; height: 280px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); }
.chart-axis { stroke: #c5d3dd; stroke-width: 1; }
.chart-grid { stroke: #e3ebf0; stroke-width: 1; }
.chart-threshold { stroke: var(--red); stroke-width: 1.5; stroke-dasharray: 5 5; }
.chart-ppm { fill: none; stroke: var(--amber); stroke-width: 2.6; }
.chart-adc { fill: none; stroke: var(--blue); stroke-width: 2; opacity: .72; }
.chart-dot { fill: var(--amber); stroke: #fff; stroke-width: 1.5; }
.chart-label { fill: var(--muted); font-size: 11px; }
.alert-list { display: grid; gap: 8px; max-height: 390px; overflow: auto; }
.alert-item { border: 1px solid var(--line); border-left: 4px solid var(--amber); border-radius: 7px; padding: 9px 10px; background: var(--panel-2); }
.alert-line { display: flex; justify-content: space-between; gap: 10px; font-weight: 700; }
.alert-meta, .alert-desc { color: var(--muted); font-size: 12px; margin-top: 4px; }
.control { padding: 12px; }
.control-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 10px; }
.pill { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line); border-radius: 999px; padding: 6px 10px; background: var(--panel-2); font-size: 12px; }
@media (max-width: 1100px) { .metric-grid, .gauge-grid, .layout { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) { .page-head { display: block; } .status-chip { margin-top: 10px; } .metric-grid, .gauge-grid, .layout { grid-template-columns: 1fr; } }
</style>
        """,
        unsafe_allow_html=True,
    )


def render_header(state: dict[str, Any]) -> None:
    pipeline = state["pipeline"]
    online = pipeline.network._online if hasattr(pipeline.network, "_online") else False
    status_text = "在线" if state["running"] else "停止"
    dot_class = "ok" if state["running"] else "bad"
    last_seen = short_time(getattr(pipeline.network, "_last_heartbeat_ts", 0.0))
    st.markdown(
        f"""
<div class="page-head">
  <div>
    <div class="title">烟雾检测边缘单元 CPS</div>
    <div class="subtitle">节点自身的实时视频、模拟烟雾传感器和本地报警状态</div>
  </div>
  <div class="status-chip"><span class="dot {dot_class}"></span>{status_text} · 网络 {"在线" if online else "离线"} · 心跳 {last_seen}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(state: dict[str, Any]) -> None:
    pipeline = state["pipeline"]
    sensor = state["sensor"]
    latest = state["last_alert"]
    ppm = sensor.get("simulated_sensor", 0.0)
    adc = sensor.get("adc", 0.0)
    fused = sensor.get("fused", float(latest.confidence) if latest else 0.0)
    threshold = sensor.get("threshold", float(ALERT_CONFIG.smoke_sensor_alarm_ppm))
    alert_count = pipeline.stats.alerts
    frame_count = pipeline.stats.frames
    alert_type = latest.alert_type if latest else "无"
    st.markdown(
        f"""
<div class="metric-grid">
  <div class="metric {'ok' if state['running'] else 'danger'}">
    <div class="metric-label">运行状态</div>
    <div class="metric-value">{"运行中" if state["running"] else "已停止"}</div>
    <div class="metric-note">本地边缘节点</div>
  </div>
  <div class="metric {'danger' if ppm >= threshold and latest else 'ok'}">
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
    <div class="metric-label">最近事件</div>
    <div class="metric-value">{esc(alert_type)}</div>
    <div class="metric-note">{short_time(latest.timestamp) if latest else "-"}</div>
  </div>
  <div class="metric">
    <div class="metric-label">帧 / 告警</div>
    <div class="metric-value">{frame_count} / {alert_count}</div>
    <div class="metric-note">本次会话</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_video(state: dict[str, Any]) -> None:
    pipeline = state["pipeline"]
    frame = pipeline.last_frame
    if frame is None:
        st.markdown('<div class="panel"><div class="section-head"><div class="section-title">实时视频</div><div class="section-note">尚未采集到画面</div></div></div>', unsafe_allow_html=True)
        return
    st.markdown(
        f"""
<div class="panel">
  <div class="section-head">
    <div class="section-title">实时视频</div>
    <div class="section-note">frame #{frame.frame_id} · {short_time(frame.timestamp)}</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )
    st.image(frame_for_streamlit(frame.raw_frame), use_container_width=True, clamp=True)


def render_gauge(title: str, value: float, unit: str, note: str, percent: float) -> str:
    pct = min(100.0, max(0.0, percent))
    return f"""
<div class="gauge">
  <div class="gauge-top"><span>{esc(title)}</span><span>{esc(note)}</span></div>
  <div class="gauge-value">{value:.2f}{esc(unit)}</div>
  <div class="bar"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>
</div>
    """


def render_sensor(state: dict[str, Any]) -> None:
    rows = list(st.session_state.get("sensor_history", []))
    latest = rows[-1] if rows else {"ppm": 0.0, "adc": 0.0, "fused": 0.0, "threshold": ALERT_CONFIG.smoke_sensor_alarm_ppm}
    max_ppm = max(latest["threshold"] * 1.25, latest["ppm"], 1.0)
    gauges = "".join(
        [
            render_gauge("烟雾浓度", latest["ppm"], " ppm", "模拟传感器", latest["ppm"] / max_ppm * 100.0),
            render_gauge("ADC", latest["adc"], "", "0-1023", latest["adc"] / 1023.0 * 100.0),
            render_gauge("融合置信度", latest["fused"], "", "视频 + 传感器", latest["fused"] * 100.0),
        ]
    )
    st.markdown(
        f"""
<div class="panel">
  <div class="section-head">
    <div class="section-title">传感器融合状态</div>
    <div class="section-note">阈值 {latest["threshold"]:.0f} ppm</div>
  </div>
  <div class="gauge-grid">{gauges}</div>
        """,
        unsafe_allow_html=True,
    )
    render_trend_chart(rows or [{"time": "-", "ppm": 0.0, "adc": 0.0, "fused": 0.0, "threshold": latest["threshold"]}])
    st.markdown("</div>", unsafe_allow_html=True)


def render_trend_chart(rows: list[dict[str, Any]]) -> None:
    threshold = rows[-1].get("threshold", ALERT_CONFIG.smoke_sensor_alarm_ppm)
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


def render_alerts(state: dict[str, Any]) -> None:
    alerts = list(reversed(st.session_state.get("alert_history", [])))
    if not alerts:
        st.markdown('<div class="empty">暂无烟雾报警记录</div>', unsafe_allow_html=True)
        return
    items = []
    for alert in alerts[:12]:
        sensor = alert.get("sensor", {})
        items.append(
            f"""
<div class="alert-item">
  <div class="alert-line">
    <span>{esc(alert.get("type", "unknown"))}</span>
    <span>{float(alert.get("confidence", 0.0)):.2f}</span>
  </div>
  <div class="alert-meta">{esc(alert.get("time", "-"))} · {esc(alert.get("level", "normal"))}</div>
  <div class="alert-desc">
    {esc(alert.get("description", ""))}<br>
    ppm={float(sensor.get("simulated_sensor", 0.0)):.0f} · adc={float(sensor.get("adc", 0.0)):.0f} · fused={float(sensor.get("fused", alert.get("confidence", 0.0))):.2f}
  </div>
</div>
            """
        )
    st.markdown(f'<div class="alert-list">{"".join(items)}</div>', unsafe_allow_html=True)


def render_controls() -> None:
    st.markdown(
        """
<div class="control">
  <div class="section-head">
    <div class="section-title">本地控制</div>
    <div class="section-note">仅控制边缘节点自身</div>
  </div>
  <div class="control-row">
    <span class="pill">模型阈值: 0.35</span>
    <span class="pill">冷却: 3s</span>
    <span class="pill">烟雾阈值: 300ppm</span>
    <span class="pill">最小命中: 2</span>
  </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("启动监测", use_container_width=True):
            start_monitoring()
            st.rerun()
    with c2:
        if st.button("停止监测", use_container_width=True):
            stop_monitoring()
            st.rerun()

    if st.button("采集一帧", use_container_width=True):
        start_monitoring()
        step_pipeline()
        st.rerun()

    st.caption("这个页面不负责远程下发，只负责本地边缘节点运行、观察和停止/启动。")
    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    inject_css()
    pipeline = ensure_pipeline()
    if st.session_state.get("edge_running"):
        step_pipeline()

    state = get_current_state()
    render_header(state)
    if st.session_state.get("last_error"):
        st.error(f"边缘节点运行错误：{st.session_state.last_error}")
    render_metrics(state)

    video_col, side_col = st.columns([1.7, 1.0], gap="medium")
    with video_col:
        render_video(state)
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        render_sensor(state)
    with side_col:
        st.markdown('<div class="panel"><div class="section-head"><div class="section-title">本地报警记录</div><div class="section-note">最近一次报警</div></div>', unsafe_allow_html=True)
        render_alerts(state)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        render_controls()

    if st.session_state.get("edge_running"):
        time.sleep(0.15)
        st.rerun()


if __name__ == "__main__":
    main()
