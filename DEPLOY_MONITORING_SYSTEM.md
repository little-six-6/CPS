# 单视频单检测智能车间安全监控系统部署指南

## 1. 安装依赖

在 `D:\edge_side` 下执行：

```powershell
pip install streamlit opencv-python numpy ultralytics
```

如果只做流程联调，没有 GPU 或模型环境，也可以先不安装 `ultralytics`，系统会进入 fallback 模式。

## 2. 启动监控中心

终端 1：

```powershell
python -m monitor_center.server
```

监控中心会同时监听：

```text
TCP: 5001, 5003, 5005, 5007
UDP: 5000, 5002, 5004, 5006
```

终端 2：

```powershell
streamlit run monitor_center/streamlit_app.py
```

浏览器打开：

```text
http://localhost:8501
```

## 3. 启动四个检测节点

四个节点都使用笔记本内置摄像头 `camera_id=0`，但通过共享帧文件避免多进程同时抢占摄像头。

终端 3：

```powershell
cd edge_side
python run_fire.py --server-ip 127.0.0.1
```

终端 4：

```powershell
cd edge_side
python run_smoking.py --server-ip 127.0.0.1
```

终端 5：

```powershell
cd edge_side
python run_ppe.py --server-ip 127.0.0.1
```

终端 6：

```powershell
cd edge_side
python run_fall.py --server-ip 127.0.0.1
```

也可以用 `--iterations 100` 做有限次数测试。

## 4. 节点端口

| 节点 | node_id | 检测类型 | UDP | TCP |
| --- | --- | --- | --- | --- |
| 火焰烟雾 | fire-smoke-001 | fire_smoke | 5000 | 5001 |
| 吸烟 | smoking-001 | smoking | 5002 | 5003 |
| 安全帽 | helmet-001 | helmet | 5004 | 5005 |
| 跌倒 | fall-001 | fall | 5006 | 5007 |

## 5. 摄像头共享机制

`CameraCapture` 在 `shared_mode=True` 时启用共享机制：

- 第一个启动并拿到 `runtime/shared_camera/camera_owner.lock` 的节点负责打开真实摄像头。
- owner 节点持续写入 `runtime/shared_camera/latest.jpg`。
- 其他节点不再直接打开摄像头，而是读取最新共享帧。
- 如果 owner 超过 `shared_stale_seconds` 未更新，后续节点可以接管摄像头。

这种方式保留了四个独立节点进程，同时避免 Windows/OpenCV 下多个进程同时打开内置摄像头导致失败。

## 6. 测试

基础冒烟测试：

```powershell
cd edge_side
python test_four_nodes.py
```

协议和监控中心语法测试：

```powershell
python -m compileall edge_side monitor_center
```

## 7. 远程控制

在 Streamlit 页面底部 `系统设置` Tab 中选择节点，发送：

- `confidence_threshold`
- `alert_cooldown_seconds`

监控中心会通过对应 TCP 连接把配置命令转发到指定节点。

