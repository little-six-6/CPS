# 智能车间安全监控中心

这是系统级 CPS 监控中心，负责接收 4 个单元级 CPS 节点的视频、告警、心跳和注册信息，并提供 Streamlit 监控界面。

## 运行

安装依赖：

```bash
pip install streamlit opencv-python numpy
```

启动监控中心服务：

```bash
python -m monitor_center.server
```

启动界面：

```bash
streamlit run streamlit_app.py
```

## 协议

帧格式：

```text
| 帧头(2B AA55) | 类型(1B) | 节点ID(16B) | 数据长度(4B big-endian) | 数据 | CRC32(4B) |
```

类型：

- `0x01` 注册
- `0x02` 心跳
- `0x03` 告警
- `0x04` 视频
- `0x05` 推理结果
- `0x06` 远程控制

注册和心跳载荷建议使用 JSON：

```json
{"node_type":"smoking"}
```

告警载荷示例：

```json
{
  "alert_type": "fire",
  "confidence": 0.92,
  "timestamp": 1710000000.0,
  "description": "fire detected",
  "frame_snapshot": "base64-jpeg"
}
```

## 数据库

SQLite 数据库默认写入：

```text
monitor_center/data/monitor_center.db
```

包含：

- `nodes`
- `alert_logs`
- `statistics`

## 兼容模式

服务端也兼容当前边缘端的旧格式：

- TCP 直接发送 JSON 告警包
- UDP 直接发送 JPEG 字节

旧 UDP 视频无法携带节点 ID，服务端会按来源 IP 生成 `legacy-<ip>` 节点。

