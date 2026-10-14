# 相机方位核实取证（2026-10-15）

> 用途：闭环计划书 Q5 / T3.5 —— `video1`/`video2` 与物理前/后的映射核实。

## 结论

| 流 | 设备 | 方位 | 画面内容 | 取证帧 |
|---|---|---|---|---|
| `rtsp://127.0.0.1:8554/video1` | `/dev/video0` | **前路** | 开放实验区视角（桌椅 / 货架 / 无人机架） | `cam-video1.jpg` |
| `rtsp://127.0.0.1:8554/video2` | `/dev/video2` | **后路** | 白色柜门特写（右侧工具挂板） | `cam-video2.jpg` |

- 判定方式：196 上从两路 RTSP 各抓一帧（ffmpeg `-frames:v 1`），**用户目视确认**；
- 前端 `VideoPanel.vue` 的"前相机 / 后相机"按钮映射（前=video1 / 后=video2）与之一致，无需改动；
- 相机型号 `SM_USB_107X`（0bda:3035），实时流 800×600@30fps H.264。

## 抓帧命令（复现用）

```bash
# 在 196 上（机器人需已唤醒，相机通电）
ffmpeg -hide_banner -loglevel error -rtsp_transport tcp \
  -i rtsp://127.0.0.1:8554/video1 -frames:v 1 -q:v 3 -y /tmp/cam_video1.jpg
ffmpeg -hide_banner -loglevel error -rtsp_transport tcp \
  -i rtsp://127.0.0.1:8554/video2 -frames:v 1 -q:v 3 -y /tmp/cam_video2.jpg
```
