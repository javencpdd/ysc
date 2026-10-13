# RTMP 推流到 SRS 可行性评估与改造方案

> 目标：把 `rtsp_stream` 项目改造为向 [SRS](https://github.com/ossrs/srs) 推送 RTMP 流
> 日期：2026-09-04
> 结论：**不需要改协议栈。ZLMediaKit 已内置 RTMP 推流客户端，一条 HTTP 请求即可。**

---

## 0. 摘要

| 问题 | 结论 |
|------|------|
| 项目里有 RTMP 实现代码吗？ | **没有源码**，但二进制里已编译进完整实现 |
| 现有协议是什么？ | 推流端用 **RTSP/AVP/TCP**（`rtspclientsink`） |
| 服务端支持 RTMP 吗？ | **支持**。MediaMTX 与 ZLMediaKit 都有完整 SRS 兼容的 RTMP 服务端 |
| 有 RTMP 客户端推流能力吗？ | **有**。`RtmpPusher.cpp` + `addStreamPusherProxy` API（`schema=rtmp`） |
| 需要改协议栈吗？ | **不需要** |
| 推荐方案 | **路径 A：ZLMediaKit 转推，零代码** |
| 工作量 | 路径 A：0 人日；路径 B：0.5 人日；路径 C（自研）：3~10 人日 |

---

## 1. 前提核实：本目录不含源码

在你要求"基于实际代码给出结论"之前，必须先确认这一点。三种方式交叉验证：

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 源码文件 | `find . -name "*.c" -o -name "*.cpp" -o -name "*.h" -o -name "*.go"` | **0 个** |
| 版本库 | `ls .git` | **不存在** |
| 构建系统 | `ls Makefile CMakeLists.txt go.mod` | **不存在** |
| 全部文本文件 | — | 仅 3 个 shell 脚本 + 2 份配置 + 2 份日志 + 前端静态资源 |

**因此"定位实现文件并修改核心模块"在本目录内无法执行。** RTMP 的源码在上游仓库：

| 组件 | 源码位置 |
|------|---------|
| MediaMTX RTMP | `github.com/bluenviron/mediamtx` → `internal/protocols/rtmp/` |
| ZLMediaKit RTMP | `github.com/ZLMediaKit/ZLMediaKit` → `src/Rtmp/` |
| GStreamer rtmpsink | `gst-plugins-bad` → `gst/rtmp/` |

### 1.1 但可以从二进制确认实现已存在

`strings` 提取编译期残留符号，精确定位：

**MediaMTX（Go）**
```
internal/protocols/rtmp/handshake/          C0/C1/C2/S0/S1/S2 握手
internal/protocols/rtmp/chunk/chunk/        Chunk 分块编解码
internal/protocols/rtmp/message/command/    AMF 命令消息
internal/protocols/rtmp/message/video/      视频消息
internal/protocols/rtmp/message/audio/      音频消息
internal/protocols/rtmp/rawmessage/         原始消息读写
internal/servers/rtmp/                      RTMP 服务端
```

**ZLMediaKit（C++）**
```
src/Rtmp/RtmpProtocol.cpp        握手 + Chunk
src/Rtmp/RtmpSession.cpp         会话状态机
src/Rtmp/RtmpPusher.cpp          ★ RTMP 推流客户端
src/Rtmp/RtmpMediaSourceImp.cpp  RTMP 媒体源
src/Rtmp/amf.cpp                 AMF0 / AMF3 编解码
src/Rtmp/FlvMuxer.cpp            FLV tag 封装
src/Rtmp/RtmpMuxer.cpp           RTMP 封装
```

符号级证据：
```
AMF0  AMF3  AMFDecoder  RtmpChunk  RtmpAudioCodec  RtmpAACPacketType
RtmpPusher12send  RtmpPusher17send ...
```

### 1.2 关键发现：现成的 RTMP 推流入口

`www/swagger/openapi.json` 中：

```
POST /index/api/addStreamPusherProxy
  secret   api 密钥
  schema   推流协议，支持 rtsp、rtmp   ← 就是这里
  vhost    __defaultVhost__
  app      live
  stream   test
  dst_url  推流地址，与 schema 一致
```

**这意味着把它推给 SRS 只需要一条 curl，不需要写任何代码。**

---

## 2. 【问题 1】现有 RTSP 与 RTMP 的协议差异

当前推流端 `push_video.sh` 用的是 **RTSP/AVP over TCP**（`rtspclientsink`），与 RTMP 是两套完全不同的体系。

### 2.1 连接建立

| 环节 | RTSP（现状） | RTMP（目标） |
|------|-------------|-------------|
| 传输层 | TCP | TCP |
| 握手 | 无专门握手。三次握手后直接发文本请求 | **C0/C1/C2 + S0/S1/S2 六段握手**，共 3+1536+1536 字节 |
| 握手内容 | — | C0/S0：1 字节版本号(0x03)<br>C1/S1：4 字节时间戳 + 4 字节零 + 1528 字节随机数<br>C2/S2：回显对端的 time+random |
| 建流方式 | `OPTIONS`→`DESCRIBE`→`SETUP`→`RECORD` 文本方法 + SDP | AMF0 编码的 `connect`→`createStream`→`publish` 命令 |
| 端口协商 | `Transport:` 头协商 RTP/RTCP 端口对（或 TCP interleaved） | 无。全部复用同一条 TCP，靠 Chunk Stream ID 区分 |

**RTMP 握手的坑**：SRS 支持简单握手，也支持带 HMAC-SHA256 的复杂握手并自动降级。自研时直接发简单握手即可（C1 的时间戳可填 0，随机数填 0 也能过），但**必须发满 1536 字节**，短了会被断开。

### 2.2 消息分块

| 维度 | RTSP/RTP | RTMP Chunk |
|------|----------|-----------|
| 单元 | RTP 包（12 字节固定头） | Chunk（Basic Header + Message Header + Payload） |
| 分片 | NALU 大时由 RFC 6184 的 FU-A 分片 | 按 chunk_size 切分（默认 128，通常由 `Set Chunk Size` 调到 4096~60000） |
| 头部开销 | 12 字节/包 | Type 0: 11 字节<br>Type 1: 7 字节<br>Type 2: 3 字节<br>Type 3: 0 字节（增量压缩） |
| 多路复用 | 靠 SSRC + 端口对 | 靠 Chunk Stream ID (CSID) + Message Stream ID (MSID) 两层 |

**Chunk Basic Header**（1~3 字节）
```
fmt(2 bits) | csid(6 bits)
  fmt=0 → Message Header 11 字节（完整）
  fmt=1 → 7 字节（省略 MSID）
  fmt=2 → 3 字节（只有 timestamp delta）
  fmt=3 → 0 字节（全沿用上一个 chunk）
  csid=0 → 再读 1 字节，csid = 64 + b
  csid=1 → 再读 2 字节（小端），csid = 64 + b0 + b1*256
```

**CSID 惯例**（SRS 都能接受，但建议遵守）
```
2   控制消息（Set Chunk Size / Window Ack Size / Set Peer Bandwidth）
3   命令消息（connect / createStream / publish）
4   音频（ffmpeg 惯例）
6   视频（ffmpeg 惯例）
8   音频（部分实现）
```

**Message Type ID**
```
1   Set Chunk Size        5   Window Acknowledgement Size
2   Abort                 6   Set Peer Bandwidth
3   Acknowledgement       4   User Control
8   Audio                 9   Video
18  AMF0 Data (onMetaData)   20  AMF0 Command
15  AMF3 Data                17  AMF3 Command
22  Aggregate Message
```

### 2.3 AMF0 / AMF3 命令消息

RTSP 用纯文本（SDP + 方法行），RTMP 用 **AMF0** 二进制编码。推流到 SRS 的完整命令序列：

```
C→S  connect           {app, tcUrl, flashVer, type:"nonprivate"}   MSID=0, CSID=3
S→C  Window Ack Size   (type 5)
S→C  Set Peer Bandwidth(type 6)
S→C  Set Chunk Size    (type 1)
S→C  _result           {fmsVer:"FMS/3,0,1,123", capabilities:31}   回应 transaction ID=1
C→S  releaseStream     (可选，Flash 兼容)
C→S  FCPublish         (可选，Flash 兼容)
C→S  createStream                                                    transaction ID=2
S→C  _result           → 返回 stream ID（通常为 1）                  ★ MSID 从这里来
C→S  publish           {stream name, type:"live"}                    MSID=<上一步返回>
S→C  onStatus          "NetStream.Publish.Start"                     ★ 收到这条才算成功
C→S  @setDataFrame / onMetaData  (type 18, AMF0 Data)
C→S  AVC sequence header (type 9, AVCPacketType=0)   ★ 必须先发 SPS/PPS
C→S  音视频数据循环      (type 8 / type 9)
```

**AMF0 类型标记**
```
0x00 Number(8B)    0x01 Boolean(1B)   0x02 String(2B len + UTF-8)
0x03 Object(键值对，以 0x00 0x00 0x09 结束)
0x05 Null          0x08 ECMA Array(4B 元素数 + 键值对 + 结束符)
0x0A Strict Array  0x0B Date          0x0C Long String(4B len)
```

AMF3 只在 type 15/17 消息中使用，且第一个字节是 `0x00` 表示 AMF0 模式。**推流到 SRS 全程用 AMF0 即可**，不需要 AMF3（ZLMediaKit 虽然编了 AMF3，但推流路径默认 AMF0）。

### 2.4 音视频数据封装

这是差异最大、最容易出错的地方。

**RTMP 视频 tag（type 9）**
```
1 字节  FrameType(4b) + CodecID(4b)
        FrameType: 1=IDR, 2=非IDR, 3=disposable, 4=generated keyframe, 5=video info
        CodecID:   7=H.264/AVC, 12=H.265/HEVC
1 字节  AVCPacketType
        0 = AVC sequence header（SPS/PPS，AVCC 格式）
        1 = AVC NALU
        2 = AVC end of sequence
3 字节  CompositionTime / CTS（有符号 int24，PTS - DTS，单位毫秒）
N 字节  AVCC 格式 NALU：4 字节长度前缀 + NALU 数据
```

**RTMP 音频 tag（type 8）**
```
1 字节  SoundFormat(4b) + SoundRate(2b) + SoundSize(1b) + SoundType(1b)
        SoundFormat: 10=AAC, 7=G711A, 8=G711U, 11=Speex
1 字节  AACPacketType
        0 = AAC sequence header（AudioSpecificConfig）
        1 = AAC raw
```

**⚠ 最容易踩的坑：AVCC vs Annex-B**

H.264 有两种 NALU 存储格式：

| 格式 | 特征 | 用在哪 |
|------|------|--------|
| **Annex-B** | `00 00 00 01` 起始码分隔 | RTP/RTSP、MP4 之外多数场合、`mpph264enc` 默认输出 |
| **AVCC** | 4 字节大端长度前缀 | **RTMP/FLV、MP4** |

`mpph264enc` 输出的是 **Annex-B（byte-stream）**，直接塞进 FLV 会导致 SRS 解不出画面。必须转换，并且**第一个视频 tag 必须是 AVCPacketType=0 携带 SPS/PPS**，否则 SRS 收到 NALU 也无法初始化解码器。

GStreamer 里用 capsfilter 强制转换：
```bash
! h264parse ! video/x-h264,stream-format=avc,alignment=au ! flvmux
```

### 2.5 时间戳与流 ID

| 字段 | RTSP/RTP | RTMP |
|------|----------|------|
| 时间基准 | 视频 90000 Hz，音频用采样率（如 48000 Hz） | 统一 **1000 Hz（毫秒）** |
| 位宽 | 32 位无符号 | 24 位存于 Message Header；≥ 0xFFFFFF 时填 0xFFFFFF 并追加 **4 字节 Extended Timestamp** |
| 语义 | 绝对时间戳（随机偏移 + 增量） | 第一个包发绝对值，后续发**增量（delta）**，靠 fmt=1/2/3 压缩 |
| 额外时间信息 | RTP marker 位 | 视频 tag 内 3 字节 **CompositionTime (CTS)**，处理 B 帧时必需 |
| 流标识 | **SSRC**（32 位随机） + RTP/RTCP 端口对 | **MSID**（4 字节小端，`createStream` 返回；控制/命令消息 MSID=0）<br>**CSID**（Chunk 通道，逻辑复用） |

**注意 MSID 字节序**：RTMP 头里绝大多数字段是大端（网络序），**唯独 Message Stream ID 是小端**。这是 RTMP spec 的历史遗留，自研时极易搞错。

---

## 3. 【问题 2】需要改动的核心模块与接口

由于本目录无源码，真正的改动点取决于选哪条路径。

### 3.1 路径 A：ZLMediaKit 转推（零代码）

| 模块 | 改动 | 说明 |
|------|------|------|
| 连接管理 | 无 | ZLMediaKit 的 `RtmpPusher` 负责建连、握手、重连 |
| 协议解析 | 无 | `RtmpProtocol.cpp` 内部完成 |
| 数据封装 | 无 | `FlvMuxer.cpp` / `RtmpMuxer.cpp` 完成 H.264 → FLV tag |
| 错误处理 | 无 | 内部处理，通过 `delStreamPusherProxy` 或 hook 感知 |
| **业务侧** | **一条 HTTP** | `addStreamPusherProxy`，见 §4.1 |

### 3.2 路径 B：GStreamer 直推（改一行管道）

| 模块 | 改动 | 说明 |
|------|------|------|
| 采集/编码 | 无 | `v4l2src → jpegdec → videoconvert → mpph264enc` 不变 |
| **封装** | `rtspclientsink` → `h264parse ! capsfilter ! flvmux` | **必须加 avc capsfilter**（§2.4） |
| **输出** | → `rtmpsink` | 替换 sink 元素 |
| 连接管理 | 无 | `rtmpsink` 内部（librtmp 兼容实现）完成握手与重连 |

### 3.3 路径 C：自研 RTMP 客户端（不推荐）

需要实现的模块：

```
rtmp_client.h
├── 连接管理   rtmp_connect() / rtmp_close() / 自动重连 + 退避
├── 握手       handshake_c0c1c2()  1536 字节，简单握手
├── Chunk      chunk_write(basic_hdr + msg_hdr + ext_ts + payload)
│              chunk_size 协商与 Set Chunk Size 响应
├── AMF0       amf0_write_number/string/object/ecma_array
├── 命令       cmd_connect() / cmd_create_stream() / cmd_publish()
│              等待 _result 与 onStatus，含超时
├── 封装       video_tag(h264) 含 AVCPacketType/CTS/AVCC 转换
│              audio_tag(aac)   含 AAC sequence header
├── 元数据     onMetaData（duration/width/height/videocodecid/...）
└── 错误处理   连接断开、send 失败、服务端 _error、超时重连
```

---

## 4. 【问题 3 / 4】可行性与分步改造方案

### 4.1 路径 A（推荐）：ZLMediaKit 转推到 SRS

**工作量：0 人日。改动：零。**

拓扑：
```
摄像头 → 硬编 → RTSP → 本地 ZLMediaKit:554/live/test
                              ↓ addStreamPusherProxy (schema=rtmp)
                          SRS:1935/live/robot01
```

步骤：

**① 确认本地 ZLMediaKit 已有流**
```bash
curl -s "http://127.0.0.1/index/api/getMediaList?secret=<你的secret>"
```

**② 发起转推**
```bash
curl -s "http://127.0.0.1/index/api/addStreamPusherProxy" \
  -d "secret=<你的secret>" \
  -d "schema=rtmp" \
  -d "vhost=__defaultVhost__" \
  -d "app=live" \
  -d "stream=test" \
  -d "dst_url=rtmp://<SRS_IP>:1935/live/robot01"
```
返回 JSON 里的 `data.key` 用于后续停止转推。

**③ 在 SRS 侧验证**
```bash
ffplay rtmp://<SRS_IP>:1935/live/robot01
```

**④ 停止转推**
```bash
curl -s "http://127.0.0.1/index/api/delStreamPusherProxy" \
  -d "secret=<你的secret>" -d "key=<上一步的key>"
```

**优点**
- 零代码，不用重新编译任何东西
- `RtmpPusher` 是 ZLMediaKit 久经考验的实现，与 SRS 互通没有问题
- **不影响现有功能**：本地 RTSP 播放照常，转推只是多挂一路
- 断线自动重连由 ZLMediaKit 处理

**缺点**
- 多一跳本地转发，增加约几十毫秒延迟
- 机器人上要常驻跑 ZLMediaKit（105MB 二进制 + 内存）

> **注意**：`<你的secret>` 在根目录 `config.ini` 的 `[api] secret=`。当前是明文硬编码的，生产环境务必改掉（详见 `ARCHITECTURE_ANALYSIS.md` 的安全章节）。

### 4.2 路径 B：GStreamer 直推 SRS

**工作量：0.5 人日。改动：一行管道。**

```bash
gst-launch-1.0 -v \
  v4l2src device=/dev/video0 \
  ! image/jpeg,width=1280,height=720,framerate=30/1 \
  ! jpegdec ! videoconvert ! video/x-raw,format=NV12 \
  ! mpph264enc bps=1500000 gop=30 \
  ! h264parse \
  ! video/x-h264,stream-format=avc,alignment=au \
  ! flvmux streamable=true \
  ! rtmpsink location="rtmp://<SRS_IP>:1935/live/robot01 live=1" sync=false
```

关键点：
- `video/x-h264,stream-format=avc,alignment=au` —— **必须**，把 Annex-B 转 AVCC（§2.4）
- `flvmux streamable=true` —— 流式 FLV，不写 duration
- `live=1` —— 关闭 librtmp 发送缓冲，省约 1 秒延迟

**优点**：链路最短，机器人上不用跑 ZLMediaKit
**缺点**：4G 公网上 TCP 队头阻塞（见 `SRT_RTMP_4G_GUIDE.md`）

### 4.3 路径 C：自研 RTMP 客户端（仅在极端情况考虑）

**前提**：GStreamer 不可用、ZLMediaKit 不可用、且必须用自有代码。
**工作量**：3~5 人日完成基本可用；5~10 人日覆盖生产级错误处理与兼容性。

**不建议的理由**：RTMP 客户端是成熟领域，`librtmp`、`srs-librtmp`、GStreamer `rtmpsink`、FFmpeg 都久经考验。自研的收益是零，风险是协议细节（AVCC 转换、Extended Timestamp、Chunk 边界、MSID 小端）上反复踩坑。

**如果确实要自研**，建议直接调用 `srs-librtmp`（SRS 官方客户端库），而不是从零写。

---

## 5. 关键接口设计（路径 C 参考）

```c
/* ---- 连接上下文 ---- */
typedef struct {
    int   fd;
    int   chunk_size;        /* 本地发送 chunk 大小，默认 128，协商后通常 4096 */
    int   peer_chunk_size;   /* 对端 chunk 大小 */
    uint32_t msid;           /* createStream 返回的 Message Stream ID */
    uint32_t last_ts[65536]; /* 各 CSID 上一个时间戳，用于 delta 压缩 */
    rtmp_state_t state;      /* HANDSHAKE / CONNECTING / PUBLISHING / ERROR */
} rtmp_ctx_t;

/* ---- 生命周期 ---- */
int  rtmp_connect(rtmp_ctx_t *ctx, const char *url);   /* 解析 rtmp://host:port/app/stream */
int  rtmp_publish(rtmp_ctx_t *ctx);                    /* connect→createStream→publish 全流程 */
int  rtmp_send_video(rtmp_ctx_t *ctx, const uint8_t *nalu, int len,
                     uint32_t dts_ms, int is_keyframe, int cts_ms);
int  rtmp_send_audio(rtmp_ctx_t *ctx, const uint8_t *aac, int len, uint32_t dts_ms);
void rtmp_close(rtmp_ctx_t *ctx);
```

---

## 6. 核心伪代码（路径 C 参考）

### 6.1 握手

```
function handshake(fd):
    # C0 + C1
    buf = byte(0x03)                       # C0: 版本号
        + uint32_be(0)                     # C1[0:4]  时间戳
        + uint32_be(0)                     # C1[4:8]  必须为 0（SRS 会校验）
        + random_bytes(1528)               # C1[8:1536]
    send(fd, buf)                          # 共 1537 字节

    s0 = recv_exact(fd, 1)                 # 应为 0x03
    s1 = recv_exact(fd, 1536)

    # C2 = 回显 S1
    c2 = s1[0:4] + uint32_be(now_ms()) + s1[8:1536]
    send(fd, c2)

    s2 = recv_exact(fd, 1536)              # 校验 s2[4:8] == C1 的时间戳
```

### 6.2 AMF0 编码

```
function amf0_number(v):
    return byte(0x00) + double_be(v)

function amf0_string(s):
    return byte(0x02) + uint16_be(len(s)) + s

function amf0_object(pairs):
    out = byte(0x03)
    for (k, v) in pairs:
        out += uint16_be(len(k)) + k + encode(v)
    out += uint16_be(0) + byte(0x09)       # 对象结束标记
    return out
```

### 6.3 命令流程

```
function publish(ctx, app, stream_name):
    # --- connect ---
    cmd = amf0_string("connect")
        + amf0_number(1)                                   # transaction ID
        + amf0_object({
            "app":       app,                              # 例 "live"
            "tcUrl":     "rtmp://" + host + ":" + port + "/" + app,
            "flashVer":  "FMLE/3.0",
            "type":      "nonprivate",
            "fpad":      false,
            "capabilities": 15,
            "audioCodecs": 4071,
            "videoCodecs": 252,
            "videoFunction": 1
          })
    send_command(ctx, csid=3, msid=0, type_id=20, cmd)

    # --- 读取服务端控制消息，直到 _result ---
    while true:
        msg = recv_message(ctx)
        if msg.type_id == 5:  handle_window_ack_size(msg)
        if msg.type_id == 6:  handle_set_peer_bandwidth(msg)
        if msg.type_id == 1:  ctx.peer_chunk_size = parse(msg)   # 通常为 4096
        if msg.type_id == 20 and is_result(msg, tid=1):  break

    # --- createStream ---
    send_command(ctx, csid=3, msid=0, type_id=20,
                 amf0_string("createStream") + amf0_number(2) + amf0_null())
    resp = recv_message(ctx)
    ctx.msid = (uint32)amf0_decode(resp.payload)[3]       # ★ 后续所有媒体消息都要用它

    # --- publish ---
    send_command(ctx, csid=3, msid=ctx.msid, type_id=20,
                 amf0_string("publish") + amf0_number(0) + amf0_null()
                 + amf0_string(stream_name) + amf0_string("live"))

    # --- 等待 onStatus: NetStream.Publish.Start ---
    while true:
        msg = recv_message(ctx)
        if msg.type_id == 20 and on_status_is(msg, "NetStream.Publish.Start"):
            ctx.state = PUBLISHING
            return OK
```

### 6.4 视频 tag 封装与发送

```
function send_video(ctx, nalu, len, dts_ms, is_keyframe, cts_ms):
    # --- 首个 tag 必须先发 SPS/PPS (AVCPacketType=0) ---
    if not ctx.sent_seq_header:
        sps, pps = extract_from_stream(nalu)
        body = byte((1<<4) | 7)          # FrameType=1(IDR) + CodecID=7(AVC)
             + byte(0)                   # AVCPacketType = 0 (sequence header)
             + int24_be(0)               # CTS = 0
             + avcc_config(sps, pps)     # 0x01 + profile + compat + level + ...
        send_media(ctx, csid=6, type_id=9, msid=ctx.msid, dts_ms, body)
        ctx.sent_seq_header = true

    # --- 数据 tag (AVCPacketType=1) ---
    # ⚠ nalu 必须是 AVCC 格式（4 字节长度前缀）。
    #   若来自 mpph264enc 是 Annex-B（00 00 00 01 起始码），必须先转换。
    avcc = annexb_to_avcc(nalu, len)

    body = byte(((is_keyframe ? 1 : 2) << 4) | 7)   # FrameType + CodecID=7
         + byte(1)                                   # AVCPacketType = 1 (NALU)
         + int24_be(cts_ms)                          # CTS = PTS - DTS
         + avcc

    send_media(ctx, csid=6, type_id=9, msid=ctx.msid, dts_ms, body)
```

### 6.5 Chunk 封装

```
function send_media(ctx, csid, type_id, msid, ts, payload):
    # 用 fmt=1 发增量时间戳，节省 4 字节/包
    if ctx.last_ts[csid] is set:
        fmt = 1
        delta = ts - ctx.last_ts[csid]
    else:
        fmt = 0
        delta = ts

    # Basic Header: fmt(2b) + csid(6b)，csid < 64 时 1 字节
    out = byte((fmt << 6) | csid)

    if fmt == 0:
        out += int24_be(min(delta, 0xFFFFFF))
        out += uint24_be(len(payload))          # message length
        out += byte(type_id)
        out += uint32_le(msid)                  # ★ 注意：MSID 是小端！
    else:
        out += int24_be(min(delta, 0xFFFFFF))
        out += uint24_be(len(payload))
        out += byte(type_id)

    # Extended Timestamp：delta >= 0xFFFFFF 时，三字节填 0xFFFFFF 并追加 4 字节真值
    if delta >= 0xFFFFFF:
        overwrite_int24(out, 0xFFFFFF)
        out += uint32_be(delta)

    # 按 chunk_size 切片，第一片带头，后续片用 fmt=3
    offset = 0
    first = true
    while offset < len(payload):
        n = min(ctx.chunk_size, len(payload) - offset)
        if first:
            send(ctx.fd, out + payload[offset : offset+n])
            first = false
        else:
            send(ctx.fd, byte((3 << 6) | csid) + payload[offset : offset+n])
            # 每片之后若超过 chunk_size 需检查是否需要重新插 Extended Timestamp
        offset += n

    ctx.last_ts[csid] = ts
```

---

## 7. 与 SRS 互通的验证清单

| # | 检查项 | 方法 |
|---|--------|------|
| 1 | SRS 收到连接 | 看 SRS 日志 `http://<SRS_IP>:1985/console`，或 `docker logs srs` |
| 2 | 握手通过 | 日志出现 `RTMP client ip=...` |
| 3 | publish 成功 | 日志出现 `publish success`；SRS 不报 `drop for header` |
| 4 | metadata 正确 | `ffprobe rtmp://.../live/robot01` 能读出 1280x720 |
| 5 | 画面正常 | `ffplay rtmp://.../live/robot01` |
| 6 | 转封装正常 | SRS 侧能拉到 `http://.../live/robot01.flv` 与 `.m3u8` |

**常见失败与原因**

| 现象 | 原因 |
|------|------|
| SRS 报 `drop for header` | 没发 AVC sequence header，或发了但格式错 |
| 连上就断 | 握手包不足 1536 字节 |
| 有流无画面 | Annex-B 未转 AVCC；或 SPS/PPS 缺失 |
| 画面花屏/绿屏 | AVCC 长度前缀错误；或 NALU 被拆散 |
| 播放几秒后卡死 | 时间戳未用增量；或 Extended Timestamp 处理错 |
| 服务端不认流名 | MSID 字节序写成大端；或 publish 用了 `record` 而非 `live` |

---

## 8. 改造对现有功能的影响

| 路径 | 对现有局域网 RTSP 图传的影响 |
|------|---------------------------|
| **A（ZLMediaKit 转推）** | **无影响**。本地 RTSP 播放照常，转推只是额外挂一路。可随时 `delStreamPusherProxy` 撤销 |
| **B（GStreamer 直推）** | **有影响**。`push_video.sh` 的输出目标从本地 RTSP 改为远端 RTMP，局域网客户端将拉不到流。解决办法：用 `tee` 双推，或保留两个脚本分别启动 |
| **C（自研）** | 完全重写，影响最大 |

**建议**：先用路径 A 验证 SRS 侧一切正常（0 成本），确认后再决定是否值得上路径 B。

---

## 9. 一句话结论

**不要改协议栈。** ZLMediaKit 二进制里已经编好了与 SRS 完全兼容的 RTMP 推流客户端（`RtmpPusher.cpp`），通过 `addStreamPusherProxy` 接口暴露出来。你需要的不是改造，是接线。
