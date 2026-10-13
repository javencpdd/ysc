# 04 — 外部 AI 识别服务（FastAPI「AI 识别服务」v1.0.0）调研

> 调研时间：2026-10-13；对象：`http://jsxy.aihyzh.com:30881/docs`（FastAPI，OpenAPI 3.1，**无鉴权**）。
> 原始数据：`ai-vision-api-raw/`（openapi.json 368KB / capabilities.json / result.json 实测回包 / sample.jpg 测试图 / 解析脚本 params.py、parse.py）。

## 1. 它是什么

一个把图像/视频识别能力封装成 HTTP 接口的**视觉能力中台**，自带 Swagger 演示页。四类用法：

| 场景 | 接口 | 说明 |
|---|---|---|
| 推理 | `POST /api/v1/tasks/{capability_id}` | 上传一张图（或视频），返回结构化结果 + base64 结果图 |
| 实时推流 | `GET /api/v1/stream/{capability_id}` | 服务端摄像头画面接上某能力，返回 MJPEG 流，浏览器 `<img>` 直接播 |
| 抓拍一帧 | `GET /api/v1/stream/{capability_id}/snapshot` | 服务端摄像头取一帧处理后返回 JPEG，适合定时抓图 |
| 回传一帧 | `POST /api/v1/stream/{capability_id}/push` | 访问者自己的一帧发上来处理，不占服务端设备 |

## 2. 规模与结构

- **122 路径 / 123 操作**：9 个基础设施接口（health / capabilities / camera×4 / streams×2）+ 33 个能力推理接口 + 27 能力 × 3 推流接口（stream MJPEG / snapshot / push）+ 能力清单 2 个。
- **33 个能力**分两组：
  - **深度学习 18 个**（ai-03~21）：图像分类（MobileNetV2/ResNet50）、YOLOv8 检测/分割、PP-OCR、语义分割（DeepLabV3）、RetinaFace 人脸、车牌、安全帽、垃圾、**火情**、电力设备、数显表读数、交通事故、人体摔倒、道路损坏、交通标志牌等。
  - **传统视觉 15 个**（opencv-02~16）：空域滤波、边缘、轮廓、模板匹配、直方图、傅里叶、银行卡识别、OCR、特征点匹配、运动检测、目标跟踪，以及 4 个 PyTorch 训练类实验。
- 每个能力有独立接口与参数列表（类型/默认值/枚举都可在 `/docs` 试调）。

## 3. 与机器人项目的关联点（重点）

1. **推流源支持 `ros://<话题>`** —— `source` 参数可填服务端设备（`0` / `/dev/video0`）、网络流（`rtsp://` / `http://`）或 **ROS 话题**。这意味着 Lite3/M20 的 ROS 相机话题可直接作为推理输入，集成路径清晰。
2. 设备自动择优：推理走 ONNX Runtime，`device=auto/cpu/cuda`，响应回显实际 provider。
3. 摄像头连不上时返回 `503 camera_unavailable` 并说明原因，不会给"永无画面的流"。

## 4. 实测（2026-10-13）

- 内置样例 `bus.jpg` 调 `ai-04-yolov8-object-detection`（yolov8n.onnx）：**96ms** 返回 5 个检测框（person ×2 等，置信度 0.87+）+ base64 结果图。
- **实际跑在 CPU**（无 CUDA provider）——响应里的 `provider=CPUExecutionProvider` 如实回显。
- 完整回包见 `ai-vision-api-raw/result.json`。

## 5. 评估与建议

| 维度 | 结论 |
|---|---|
| 能力覆盖 | 与巡检场景对口（火情/安全帽/电力设备/摔倒/道路损坏），开箱即用 |
| 集成成本 | 低：HTTP + ros:// 话题源，无需本地部署模型 |
| 延迟 | CPU 推理 96ms/帧（720p 以内），可接受但不适合高帧率实时闭环 |
| 风险 1 | **无鉴权**：任何人拿到地址即可调用全部接口（含推流/抓拍） |
| 风险 2 | **外部依赖**：服务在公网第三方域名，可用性/版本不受我们控制；现场部署建议评估自托管同类方案（如自建 FastAPI + ONNX） |
| 风险 3 | 该服务更像教学/演示中台（能力命名"实验1~18"），生产使用前需确认 SLA 与并发能力 |

**建议**：作为"快速验证视觉想法"的试用通道保留本文档；若要接入机器人常态化巡检，优先推 `ros://` 话题源做端到端联调，同时并行评估自托管部署（模型均为公开 onnx，可自行搭建）。

## 6. 复现方式

```bash
# 列举全部能力
curl -s http://jsxy.aihyzh.com:30881/api/v1/capabilities | python -m json.tool | head -50
# 单帧推理（YOLOv8n）
curl -s -X POST "http://jsxy.aihyzh.com:30881/api/v1/tasks/ai-04-yolov8-object-detection" \
  -F "file=@sample.jpg" -F "obj_thresh=0.25" -F "nms_thresh=0.45"
```

解析脚本（`ai-vision-api-raw/params.py` 看接口参数、`parse.py` 列全量路径与能力）依赖同目录 openapi.json / capabilities.json，直接 `python` 运行即可。
