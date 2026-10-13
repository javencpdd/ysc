# RTSP 应用代码与运行机制分析报告

## 0. 结论摘要

- **当前主系统**是 `/home/ysc/rtsp_stream` 中的 **MediaMTX v1.4.2**，由 systemd 单元 `rtsp_stream.service` 启动。它不是本机可编译的源码仓库，而是“脚本 + YAML 配置 + aarch64 预编译二进制”的部署目录。
- **媒体生产端**是 GStreamer：从 `/dev/video0` 采集 MJPEG，解码、色彩转换后使用 Rockchip MPP 硬件编码为 H.264，并通过 `rtspclientsink` 发布到本机的 `rtsp://127.0.0.1:8554/test`。
- 因此对外可读的主流地址为 `rtsp://<服务器IP>:8554/test`。实测 RTSP 端口、UDP RTP/RTCP 端口已监听，服务为 active。
- `ZLMediaKit` 与 `/home/ysc/.zetton/rtsp_server` 均为**次要/遗留部署**：前者当前没有 MediaServer 进程；后者对应的 `streaming.service` 为 disabled + inactive。两者不参与当前 `/test` 流。

> 取证时间：2026-09-05（Asia/Shanghai）。  
> 证据标记：**[远端实测]** 表示来自当前主机的文件、进程、端口或 RTSP 响应；**[上游源码对照]** 表示与运行二进制精确匹配的公开 MediaMTX v1.4.2 标签源码。部署目录没有该源码，因此两者刻意区分。

## 1. 位置、入口与项目主次

### 1.1 主项目：正在运行的 RTSP 服务

| 项目 | 结论 |
|---|---|
| 远端目录 | `/home/ysc/rtsp_stream` |
| 本地 Git 元数据 | 未找到 `.git`；`git -C /home/ysc/rtsp_stream` 不能识别为工作树，因此**无法从主机给出该部署目录的 origin URL 或提交号** |
| 对应公开上游仓库 | [bluenviron/mediamtx](https://github.com/bluenviron/mediamtx.git)，运行版本 `v1.4.2`，精确标签提交 `b8b64fda80ce02d572440753462bf85d35401491` |
| systemd 入口 | `/lib/systemd/system/rtsp_stream.service:1-10` |
| 脚本入口 | `/home/ysc/rtsp_stream/start_stream.sh:1-5` |
| RTSP 服务器启动脚本 | `/home/ysc/rtsp_stream/start_server.sh:1` |
| 推流脚本 | `/home/ysc/rtsp_stream/push_video.sh:1-4` |
| 服务配置 | `/home/ysc/rtsp_stream/mediamtx.yml:1-561` |
| RTSP 服务程序 | `/home/ysc/rtsp_stream/mediamtx`（aarch64 静态 Go 可执行文件，`--version` 返回 `v1.4.2`） |

**[远端实测] systemd 与脚本调用关系**

`/lib/systemd/system/rtsp_stream.service:5-10`：

```ini
[Service]
Type=forking
ExecStart=/home/ysc/rtsp_stream/start_stream.sh

[Install]
WantedBy=network.target
```

`/home/ysc/rtsp_stream/start_stream.sh:3-5`：

```bash
cd /home/ysc/rtsp_stream
./start_server.sh &
./push_video.sh &
```

`/home/ysc/rtsp_stream/start_server.sh:1`：

```bash
sudo ./mediamtx
```

`/home/ysc/rtsp_stream/push_video.sh:3`：

```bash
sudo gst-launch-1.0 v4l2src device=/dev/video0 ! image/jpeg, width=1280, height=720, framerate=30/1 ! jpegdec ! videoconvert ! mpph264enc ! rtspclientsink location=rtsp://127.0.0.1:8554/test latency=10
```

当前存在的子进程为 `mediamtx` 与上述 `gst-launch-1.0 ... rtspclientsink`，`rtsp_stream.service` 状态为 **enabled / active**。

### 1.2 次要或遗留 RTSP 相关内容

| 优先级 | 路径 | 内容与当前状态 |
|---|---|---|
| 次要（未运行） | `/home/ysc/rtsp_stream/ZLMediaKit/MediaServer` | ZLMediaKit 预编译服务端；没有当前运行进程。历史日志 `/home/ysc/rtsp_stream/log/2024-02-26_00.log` 表明它曾启动后退出。 |
| 次要（未运行） | `/home/ysc/rtsp_stream/config.ini:132-158`、`/home/ysc/rtsp_stream/ZLMediaKit/config.ini:132-158` | ZLMediaKit 的 RTP/RTSP 配置；见第 7.4 节。主启动脚本并不调用它。 |
| 次要（禁用） | `/home/ysc/.zetton/rtsp_server/{mediamtx,mediamtx.yml}` | 另一份 MediaMTX 二进制和配置；由 `/home/ysc/.zetton/streaming.sh:1-9` 设计启动。它的 `/etc/systemd/system/streaming.service:1-16` 当前为 **disabled / inactive**。 |
| 参考样例 | `/home/ysc/jy_exe/scripts/push_video.sh:1` | 仅有一条被注释的 `gst-rtsp-server/test-launch` 试验命令，不会执行。 |

**主次判定依据**：运行进程、已启用服务、监听端口、实际 `/test` 的 SDP 均与 `/home/ysc/rtsp_stream` 相符；无 ZLMediaKit/zetton 的活动服务进程。

## 2. 当前系统结构与数据路径

```text
systemd rtsp_stream.service
        |
        v
start_stream.sh
  |                         |
  |                         +--> push_video.sh
  |                                  |
  v                                  v
start_server.sh                 /dev/video0 (MJPEG, 1280x720@30)
  |                                  |
  v                                  +--> jpegdec -> videoconvert
MediaMTX v1.4.2                         -> mpph264enc (Rockchip MPP, H.264)
  |                                              |
  | TCP :8554, UDP :8000/:8001                 rtspclientsink
  |                                              |
  +<------- RTSP publish: ANNOUNCE/SETUP/RECORD-+
  |
  +--> 路径 path: test / Stream / SDP
  |
  +--> RTSP 读者：OPTIONS -> DESCRIBE -> SETUP -> PLAY
  +--> 同源输出：RTMP :1935、HLS :8888、WebRTC :8889、SRT/UDP :8890
```

### 2.1 模块职责

| 层次 | 模块/目录 | 职责 |
|---|---|---|
| 进程编排 | `rtsp_stream.service`、`start_stream.sh` | systemd 拉起两个后台分支；当前单元未声明 `Restart=`、`User=` 或 `PIDFile=`。 |
| RTSP 服务 | `mediamtx`、`mediamtx.yml` | 接受发布者，维护 path/stream/读者，将同一媒体路由到 RTSP、HLS、RTMP、WebRTC、SRT。 |
| 摄像头/编码 | `push_video.sh` | V4L2 拉取相机的 JPEG 帧，GStreamer 解码后由 MPP 进行 H.264 硬编码。 |
| RTSP 客户端发布 | `rtspclientsink` | 将 `video/x-h264` 作为 RTSP 发布者发送到 MediaMTX；其内部承担发布端的 RTSP/RTP 封装。 |
| 协议库 | MediaMTX 内嵌的 Go 依赖 | gortsplib 负责 RTSP、RTP、RTCP 会话与传输；Pion RTP/RTCP/SDP 用于媒体与其他协议适配。 |

### 2.2 实际编码与 SDP

**[远端实测]** 对 `rtsp://127.0.0.1:8554/test` 仅执行非破坏性的 `OPTIONS` 和 `DESCRIBE`，服务器返回：

```rtsp
RTSP/1.0 200 OK
Public: DESCRIBE, ANNOUNCE, SETUP, PLAY, RECORD, PAUSE, GET_PARAMETER, TEARDOWN
Server: gortsplib

v=0
o=- 0 0 IN IP4 127.0.0.1
s=Session streamed with GStreamer
c=IN IP4 0.0.0.0
t=0 0
m=video 0 RTP/AVP 96
a=control:rtsp://127.0.0.1:8554/test/trackID=0
a=rtpmap:96 H264/90000
a=fmtp:96 packetization-mode=1; profile-level-id=64C028;
  sprop-parameter-sets=<SPS-base64>,<PPS-base64>
```

由此可知当前 path 是 `test`，只有**一个视频 track**、没有音频；有效载荷类型为动态 PT 96，编解码为 H.264，RTP 时钟为 90 kHz。SPS/PPS 在 SDP 中以 `sprop-parameter-sets` 传递；报告中已省略具体参数集值。插件检查还确认 `mpph264enc` 来自 `/usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstrockchipmpp.so`，版本 1.14.4，输出能力为 `video/x-h264, stream-format=byte-stream, alignment=au`。

## 3. RTSP 信令、SDP 与媒体流的执行流程

### 3.1 读者（拉流）流程

下面的 OPTIONS 与 DESCRIBE 已实测；SETUP/PLAY/PAUSE/TEARDOWN 的状态动作由当前二进制版本对应的上游源码核对。

| 阶段 | 请求/动作 | 当前服务的处理 |
|---|---|---|
| 1 | `OPTIONS rtsp://.../test` | gortsplib 返回能力集合；实测包含 DESCRIBE、ANNOUNCE、SETUP、PLAY、RECORD、PAUSE、TEARDOWN。 |
| 2 | `DESCRIBE` | `conn.onDescribe()` 校验 path、建立认证 nonce，经 `pathManager.Describe()` 查找 stream，返回 SDP 和 `gortsplib.ServerStream`。当前返回第 2.2 节 H.264 SDP。 |
| 3 | `SETUP trackID=0` | `session.onSetup()` 校验 path 和 Transport；经 `pathManager.AddReader()` 鉴权/登记读者，返回带 Session/Transport 的 200 与 ServerStream。 |
| 4 | `PLAY` | `session.onPlay()` 从 PrePlay 变为 Play，记录协商 transport，触发可选 `runOnRead` hook（本机配置为空），gortsplib 开始把 stream 的 RTP 交给该会话。 |
| 5 | `PAUSE` | 读会话调用 `onUnreadHook()`，状态回到 PrePlay，保留会话；再次 PLAY 可恢复。 |
| 6 | `TEARDOWN` 或 TCP 断开/超时 | gortsplib 关闭 ServerSession，MediaMTX 的 `Server.OnSessionClose()` 调用 `session.onClose()`，将读者从 path 移除并清空引用。 |

**[上游源码对照] 读者分派入口**  
MediaMTX v1.4.2 的 `internal/servers/rtsp/server.go:245-281` 将 gortsplib 回调转发给 `conn.onDescribe` 与 `session.onSetup/onPlay/onPause`：

```go
func (s *Server) OnDescribe(ctx *gortsplib.ServerHandlerOnDescribeCtx)
    (*base.Response, *gortsplib.ServerStream, error) {
    c := ctx.Conn.UserData().(*conn)
    return c.onDescribe(ctx)
}

func (s *Server) OnSetup(ctx *gortsplib.ServerHandlerOnSetupCtx)
    (*base.Response, *gortsplib.ServerStream, error) {
    c := ctx.Conn.UserData().(*conn)
    se := ctx.Session.UserData().(*session)
    return se.onSetup(c, ctx)
}
```

来源：[server.go@v1.4.2#L245-L281](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/servers/rtsp/server.go#L245-L281)。

### 3.2 发布者（本机 GStreamer）流程

发布流比读流多出 `ANNOUNCE` 与 `RECORD`：

```text
rtspclientsink
  -> OPTIONS（常见客户端探测；具体是否发送取决于客户端实现）
  -> ANNOUNCE（携带 H.264 SDP，申请向 /test 发布）
  -> SETUP（mode=record，协商 UDP、组播或 TCP interleaved）
  -> RECORD
  -> RTP H.264 包持续送入 MediaMTX
  -> PAUSE / TEARDOWN 或连接断开
```

**注意**：脚本没有为 `rtspclientsink` 显式指定 transport；因此配置允许哪些模式可以确定，但**这一次发布者实际选中 UDP、组播还是 TCP，不能仅从脚本断言**。可通过 MediaMTX API（本机当前关闭）或 debug 日志/抓包进一步确认。

**[上游源码对照] ANNOUNCE/RECORD 把 SDP 和 RTP 接入 Stream**

```go
// internal/servers/rtsp/session.go:290-317
res := s.path.StartPublisher(defs.PathStartPublisherReq{
    Author: s, Desc: s.rsession.AnnouncedDescription(),
    GenerateRTPPackets: false,
})
s.stream = res.Stream

s.rsession.OnPacketRTP(cmedi, cforma, func(pkt *rtp.Packet) {
    pts, ok := s.rsession.PacketPTS(cmedi, pkt)
    if !ok { return }
    res.Stream.WriteRTPPacket(cmedi, cforma, pkt, time.Now(), pts)
})
```

来源：[session.go@v1.4.2#L290-L328](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/servers/rtsp/session.go#L290-L328)。

这里的 `AnnouncedDescription()` 就是发布端 ANNOUNCE 中的 SDP；它被保存在 Stream 中，随后被 DESCRIBE 用于提供给读者。

### 3.3 SDP 协商

1. GStreamer 编码端产出 H.264 access unit；`rtspclientsink` 对外发布时生成/携带 SDP。
2. MediaMTX 的 `session.onAnnounce()` 把发布者绑定到 `test` path；`onRecord()` 从 `AnnouncedDescription()` 建立 `stream.Stream`。
3. 读者的 DESCRIBE 通过 `conn.onDescribe()` 获取该 Stream 的 `gortsplib.ServerStream`；gortsplib 生成 200 和 SDP。
4. 本机的 SDP 只有 `m=video`，PT 96 映射 H.264/90000，`packetization-mode=1`，并含 SPS/PPS，因此读取端可在开始解码前配置解码器。

**[上游源码对照] Stream 保存描述并按需创建 RTSP ServerStream**

```go
// internal/stream/stream.go:21-32, 95-104
type Stream struct {
    desc       *description.Session
    smedias    map[*description.Media]*streamMedia
    rtspStream *gortsplib.ServerStream
}

func (s *Stream) RTSPStream(server *gortsplib.Server) *gortsplib.ServerStream {
    s.mutex.Lock()
    defer s.mutex.Unlock()
    if s.rtspStream == nil {
        s.rtspStream = gortsplib.NewServerStream(server, s.desc)
    }
    return s.rtspStream
}
```

来源：[stream.go@v1.4.2#L21-L32](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/stream/stream.go#L21-L32) 和 [#L95-L104](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/stream/stream.go#L95-L104)。

### 3.4 RTP / RTCP 与媒体分发

**已部署的端口与传输**

- RTSP 控制连接：TCP `:8554`。
- 单播 UDP：RTP `:8000`，RTCP `:8001`（当前两端口均已绑定）。
- 组播：配置地址段 `224.1.0.0/16`，RTP `:8002`，RTCP `:8003`。
- TCP interleaved：RTP/RTCP 帧复用在 RTSP TCP 连接中；不额外监听 UDP 媒体端口。
- 当前实测监听还包含 RTMP TCP `:1935`、HLS TCP `:8888`、WebRTC TCP `:8889` 与 SRT UDP `:8890`。

MediaMTX 自身在该版本主要将 RTSP/RTP/RTCP 线协议交给 **gortsplib v4.6.3**；MediaMTX 的 `session.onRecord()` 注册 `OnPacketRTP`，以 PTS 将入站 RTP 写入 `stream.Stream`。RTCP 发送报告、接收报告、丢包/解析错误检测由 gortsplib 会话/传输层维护；MediaMTX 暴露 `OnPacketLost`、`OnDecodeError`、`OnStreamWriteError` 回调，只进行限速告警日志记录。

**[上游源码对照] RTP 入站处理和分发**

```go
// internal/stream/stream_format.go:69-109
u, err := sf.proc.ProcessRTPPacket(pkt, ntp, pts, hasNonRTSPReaders)
if err != nil {
    sf.decodeErrLogger.Log(logger.Warn, err.Error())
    return
}

for _, pkt := range u.GetRTPPackets() {
    s.rtspStream.WritePacketRTPWithNTP(medi, pkt, u.GetNTP())
}
for writer, cb := range sf.readers {
    writer.Push(func() error {
        atomic.AddUint64(s.bytesSent, size)
        return cb(u)
    })
}
```

来源：[stream_format.go@v1.4.2#L69-L109](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/stream/stream_format.go#L69-L109)。

也就是说，RTP packet 先经 format processor 解析/规范化；同一组 RTP 包一方面写向 RTSP/RTSPS 的 `ServerStream`，另一方面通过异步 writer 交给 HLS、RTMP、WebRTC 等非 RTSP 读者。该部署未启用录制（见第 7.1 节），故不写录像分片。

## 4. 会话、连接、Path 与资源释放

### 4.1 关键数据结构

| 所在源码（上游 v1.4.2） | 类型 | 关键字段与职责 |
|---|---|---|
| `internal/servers/rtsp/server.go:46-78` | `rtsp.Server` | 持有 `*gortsplib.Server`，并维护 `conns map[*ServerConn]*conn`、`sessions map[*ServerSession]*session`。 |
| `internal/servers/rtsp/conn.go:26-45` | `conn` | 每条 TCP RTSP 连接的 UUID、认证 nonce、失败次数、连接/断连 hooks 和 PathManager 引用。 |
| `internal/servers/rtsp/session.go:25-47` | `session` | RTSP session 的 state、协商 transport、pathName、`defs.Path`、`*stream.Stream`。 |
| `internal/core/path_manager.go:81-114` | `pathManager` | 将 path 名解析为配置/动态 Path，执行 Describe、AddReader、AddPublisher 和认证。 |
| `internal/core/path.go:66-116` | `path` | 一个 path 的 source（publisher）、stream、reader 集合、按需计时器、录制与 hook。 |
| `internal/stream/stream.go:21-32` | `stream.Stream` | SDP description、media/format 索引、RTSP/RTSPS ServerStream 和流量计数器。 |
| `internal/stream/stream_format.go:25-29` | `streamFormat` | 单一编码格式的 processor 与异步读者回调表。 |

### 4.2 主要调用链

```text
gortsplib.Server event
  -> rtsp.Server.OnConnOpen / OnSessionOpen
      -> conn.initialize / session.initialize

Reader:
  OnDescribe -> conn.onDescribe -> pathManager.Describe -> path.doDescribe
  OnSetup    -> session.onSetup -> pathManager.AddReader -> path.doAddReader
  OnPlay     -> session.onPlay -> gortsplib ServerStream starts delivery

Publisher:
  OnAnnounce -> session.onAnnounce -> pathManager.AddPublisher -> path.doAddPublisher
  OnSetup    -> session.onSetup (record path returns OK)
  OnRecord   -> session.onRecord -> path.StartPublisher -> path.setReady
           -> stream.New -> session.OnPacketRTP -> Stream.WriteRTPPacket

Shutdown:
  TEARDOWN/connection close -> Server.OnSessionClose -> session.onClose
  -> Path.RemoveReader or Path.RemovePublisher
  -> path.setNotReady -> close readers / Stream.Close / stop recorder (if any)
```

**[上游源码对照] 连接、会话的创建及关闭**

```go
// internal/servers/rtsp/server.go:170-191
func (s *Server) OnConnOpen(ctx *gortsplib.ServerHandlerOnConnOpenCtx) {
    c := &conn{ /* configuration, PathManager, gortsplib conn */ }
    c.initialize()
    s.conns[ctx.Conn] = c
    ctx.Conn.SetUserData(c)
}

// internal/servers/rtsp/server.go:234-242
func (s *Server) OnSessionClose(ctx *gortsplib.ServerHandlerOnSessionCloseCtx) {
    se := s.sessions[ctx.Session]
    delete(s.sessions, ctx.Session)
    if se != nil { se.onClose(ctx.Error) }
}
```

来源：[server.go@v1.4.2#L170-L242](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/servers/rtsp/server.go#L170-L242)。

```go
// internal/servers/rtsp/session.go:74-91
func (s *session) onClose(err error) {
    if s.rsession.State() == gortsplib.ServerSessionStatePlay {
        s.onUnreadHook()
    }
    switch s.rsession.State() {
    case gortsplib.ServerSessionStatePrePlay, gortsplib.ServerSessionStatePlay:
        s.path.RemoveReader(defs.PathRemoveReaderReq{Author: s})
    case gortsplib.ServerSessionStatePreRecord, gortsplib.ServerSessionStateRecord:
        s.path.RemovePublisher(defs.PathRemovePublisherReq{Author: s})
    }
    s.path = nil
    s.stream = nil
}
```

来源：[session.go@v1.4.2#L74-L91](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/servers/rtsp/session.go#L74-L91)。

**资源回收要点**

- 读者的 TEARDOWN、异常断线和超时最终均走会话关闭，移除 reader。
- 发布者关闭时，`path.doRemovePublisher()` 调用 `executeRemovePublisher()`；若仍有 Stream，`setNotReady()` 会关闭所有 reader、record agent（若存在）和 Stream。
- `Stream.Close()` 会关闭 RTSP/RTSPS ServerStream；服务整体 `Server.Close()` 使用 context cancel 和 WaitGroup 等待 goroutine 收敛。
- 当前 path 的 `record: no`，因此运行时没有录制 agent/分片资源。

## 5. 鉴权、异常处理与可观察性

### 5.1 当前鉴权结论

**[远端实测]** `/home/ysc/rtsp_stream/mediamtx.yml` 的：

- `externalAuthenticationURL:` 为空（第 42 行）；
- `authMethods: [basic]`（第 108-110 行）；
- `publishUser/publishPass` 与 `readUser/readPass` 均为空（第 320-336 行）。

所以主 path `all_others`（包含 `test`）**当前没有配置发布或读取用户名/密码，也没有外部认证服务**。Basic 是可用机制而非已要求的凭据。并且 `encryption: "no"`，当前是明文 RTSP；若以后启用 Basic 凭据，应同步启用 RTSPS 或部署在可信网络中。

**[上游源码对照] 认证处理**

```go
// internal/core/auth.go:94-143（逻辑摘录）
if externalAuthenticationURL != "" {
    err := doExternalAuthentication(externalAuthenticationURL, accessRequest)
    if err != nil { return defs.AuthenticationError{...} }
}
if pathUser != "" {
    if accessRequest.RTSPRequest != nil && rtspAuth.Method == headers.AuthDigest {
        err := auth.Validate(/* request, user, pass, nonce */)
        ...
    } else if !checkCredential(pathUser, accessRequest.User) ||
              !checkCredential(pathPass, accessRequest.Pass) {
        return defs.AuthenticationError{Message: "invalid credentials"}
    }
}
```

来源：[auth.go@v1.4.2#L79-L143](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/core/auth.go#L79-L143)。

当认证失败时，`conn.handleAuthError()` 会先回 `401 Unauthorized` 与 `WWW-Authenticate` nonce；前三次失败仍允许客户端重试，随后等待 2 秒以减缓暴力猜测（[conn.go:181-205](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/servers/rtsp/conn.go#L181-L205)）。

### 5.2 错误路径

| 条件 | 响应/动作 | 源码位置 |
|---|---|---|
| 无效 path（没有以 `/` 开始） | 400 Bad Request | `conn.go:112-116`，`session.go:155-159` |
| 请求 TCP interleaved，但 config 禁用 TCP | 461 Unsupported Transport | `session.go:162-172` |
| 未发布 stream 的 DESCRIBE/SETUP | 404 Not Found | `conn.go:148-153`，`session.go:220-225` |
| path 不是 `source: publisher` 却发布 | 拒绝发布 | `path.go:506-511` |
| 发布者已存在且不允许覆盖 | 拒绝；当前配置反而允许覆盖 | `path.go:514-523` |
| RTP 格式处理失败 | 限速 Warn，丢弃该单元 | `stream_format.go:59-84` |
| 丢包、decode 或写流错误 | 限速 Warn | `session.go:372-385` |
| TCP 读/写超时 | 当前均为 10 秒 | `mediamtx.yml:16-18`；由 gortsplib server 使用 |

当前 config 的 `overridePublisher: yes`（`mediamtx.yml:341-342`）意味着新的发布者会关闭旧发布者并接管相同 path。这适合单摄像头恢复推流，但也是应被业务层明确接受的切换语义。

## 6. 当前关键配置清单

**[远端实测] `/home/ysc/rtsp_stream/mediamtx.yml`**

```yaml
# :75-110
rtsp: yes
protocols: [udp, multicast, tcp]
encryption: "no"
rtspAddress: :8554
rtpAddress: :8000
rtcpAddress: :8001
multicastIPRange: 224.1.0.0/16
multicastRTPPort: 8002
multicastRTCPPort: 8003
authMethods: [basic]

# :249-342 (pathDefaults)
source: publisher
sourceOnDemand: no
maxReaders: 0
record: no
publishUser:
publishPass:
readUser:
readPass:
overridePublisher: yes
```

| 配置项 | 实际值 | 含义 |
|---|---|---|
| `readTimeout` / `writeTimeout` | 10s / 10s（第 16/18 行） | RTSP I/O 超时。 |
| `writeQueueSize` | 512（第 20-22 行） | 出站写队列容量。 |
| `udpMaxPayloadSize` | 1472（第 23-25 行） | UDP RTP 单包负载上限，避免超过常见 IPv4 MTU。 |
| `paths.all_others` | 第 554、561 行 | `test` 没有单独 path，继承 `pathDefaults`。 |
| API / metrics / pprof | no（第 44-57 行） | 当前无法通过 HTTP API 查询会话/transport；分析以进程、端口、RTSP 探测及日志为准。 |
| HLS / RTMP / WebRTC / SRT | yes（第 115、136、192、240 行） | 与 RTSP Stream 共享 path，可提供多协议读取。 |

## 7. 依赖、协议栈与构建归属

### 7.1 当前主部署

| 组件 | 版本/证据 | 作用 |
|---|---|---|
| MediaMTX | v1.4.2（`mediamtx --version`） | Go 编写的媒体路由服务，监听 RTSP/RTP/RTCP 并管理 path、sessions、readers。 |
| gortsplib | v4.6.3（MediaMTX v1.4.2 的 `go.mod:11`） | RTSP server/client、RTP/RTCP、UDP/组播/TCP interleaved、Session 生命周期；响应 `Server: gortsplib` 也由实测确认。 |
| pion/rtp | v1.8.3（`go.mod:25`） | RTP Packet 类型与处理。 |
| pion/rtcp | v1.2.13（`go.mod:24`） | RTCP 结构/协议支持。 |
| pion/sdp | v3.0.6（`go.mod:26`） | SDP 处理，主要也服务 WebRTC 适配。 |
| GStreamer | `gst-launch-1.0` / `rtspclientsink` | 采集、JPEG 解码、视频转换与 RTSP 发布。 |
| Rockchip MPP 插件 | `rockchipmpp` 1.14.4，`mpph264enc` | 硬件 H.264 编码。 |
| V4L2 | `v4l2src device=/dev/video0` | 摄像头设备采集接口。 |

MediaMTX 依赖声明的权威清单见上游 [go.mod@v1.4.2](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/go.mod)；RTSP/RTP/RTCP 协议说明见其 [README 的 specifications/dependencies 段](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/README.md#specifications)。

### 7.2 端口和网络模式

| 协议 | 配置/监听 | 启用状态 |
|---|---|---|
| RTSP 控制 | TCP 8554 | 运行中 |
| RTP（单播） | UDP 8000 | 运行中 |
| RTCP（单播） | UDP 8001 | 运行中 |
| RTP/RTCP（组播） | 224.1.0.0/16，UDP 8002/8003 | 配置启用；本次未建立组播读者验证 |
| RTSP over TCP | 8554 上 interleaved | 配置允许；本次未对当前发布者的实际协商结果作断言 |
| RTSPS | 8322 | 配置字段存在但 `encryption: "no"`，未启用 |
| RTMP | TCP 1935 | 运行中 |
| HLS | TCP 8888 | 运行中 |
| WebRTC HTTP | TCP 8889 | 运行中；另有配置的 ICE UDP 8189 |
| SRT | UDP 8890 | 运行中 |

### 7.3 配置加载方式

当前启动命令是目录内的 `./mediamtx`，未在脚本上传显式 YAML 参数；MediaMTX 默认在工作目录查找 `mediamtx.yml`，而 `start_stream.sh:3` 先 `cd /home/ysc/rtsp_stream`，因此实际加载的就是同目录的 `mediamtx.yml`。MediaMTX v1.4.2 的 `core.New()` 通过 `conf.Load()` 读取配置并创建 `pathManager`、RTSP/RTMP/HLS/WebRTC/SRT 资源（[core.go:111-165](https://github.com/bluenviron/mediamtx/blob/b8b64fda80ce02d572440753462bf85d35401491/internal/core/core.go#L111-L165)）。

### 7.4 遗留 ZLMediaKit 配置（不影响当前 /test）

`/home/ysc/rtsp_stream/config.ini:132-158` 及 ZLMediaKit 子目录的同名文件具有：`[rtsp]` 端口 554、`rtpTransportType=-1`（自动）、`authBasic=0`，以及 `[rtp]` H.264 STAP-A、video MTU 1400 等配置。这是 ZLMediaKit 的另一套协议栈，不能与当前实际监听的 MediaMTX :8554 / :8000 / :8001 混同。它仅在需要恢复 MediaServer 时才有意义。

## 8. 代码定位与维护建议

1. 若需要修改**启动、摄像头、分辨率、帧率、编码器或推流 URL**，应改主目录的 `push_video.sh:3`；当前 1280×720@30、H.264 和 path `test` 都在这一行。
2. 若需要改**端口、传输模式、鉴权、TLS、path 策略、录制或多协议输出**，应改 `mediamtx.yml` 的相应行。尤其是 `paths.all_others` 覆盖了 `test`。
3. 若需修改 **MediaMTX 内部 RTSP 逻辑**，远端无本地源码可修改；应从上游仓库检出固定提交 `b8b64fda80ce02d572440753462bf85d35401491`，修改并为 aarch64 重新构建/替换二进制。不要把当前主目录误当作源代码仓库。
4. ZLMediaKit 的 `config.ini` 不会修改当前 MediaMTX 服务；除非明确切换启动链，否则不应将它作为 /test 的配置入口。
5. 当前服务采用 `Type=forking`，而脚本自行后台化两个子进程且没有 `Restart=`/PID 文件；若后续进行运维改造，应先验证 systemd 的主进程跟踪与异常恢复行为，避免把服务单元状态误当作两个子进程一定健康。

## 9. 本次分析范围与限制

- 已读取授权范围内的 `/home` 下代码/部署内容、相关 systemd 配置、Git 元数据、运行进程、端口和 RTSP OPTIONS/DESCRIBE 响应。
- 未对生产流执行 SETUP/PLAY 或抓取 RTP 包，避免新建读者改变生产会话；因此“实际发布者最终选中的 transport”不作未经证实的结论。
- 未改动服务配置、脚本、二进制或运行状态；本报告是只读分析输出。
- 未在报告中记录配置中可能存在的敏感值；如需启用 API、外部认证或 TLS，请按最小权限另行审计配置。
