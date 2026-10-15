/**
 * WHEP 拉流客户端（2026-10-16 新增）
 *
 * 用途：从 MediaMTX（196 上 v1.4.2，`webrtc: yes` / `:8889`）以 **WebRTC** 拉取相机画面。
 * 之所以走 WHEP 而不是后端 ffmpeg 转 HLS：
 *   - 延迟 1–3s → 约 0.3s；
 *   - 后端不再中转视频流（省一路 ffmpeg，CPU 更宽裕）；
 *   - 前后两路可**同时**看（旧的单路中继做不到）。
 *
 * 协议（WHEP，draft-ietf-wish-whep）：
 *   1) 建 RTCPeerConnection，加 recvonly 收发器；
 *   2) createOffer → setLocalDescription；
 *   3) **等 ICE 收集完成再发**（非 trickle，兼容性最好）；
 *   4) POST <url>，Content-Type: application/sdp，body = offer.sdp；
 *   5) 201 响应体即 answer SDP，Location 头是资源 URL（断开时 DELETE 它）；
 *   6) setRemoteDescription → ontrack 拿到媒体流。
 *
 * MediaMTX 已开 `webrtcAllowOrigin: '*'`，浏览器跨域直连无需后端代理。
 */

const ICE_GATHER_TIMEOUT_MS = 1500
const CONNECT_TIMEOUT_MS = 12000
const RETRY_MAX_DELAY_MS = 10000

export function isWebRtcSupported() {
  return typeof window !== 'undefined' && typeof window.RTCPeerConnection === 'function'
}

function waitIceGathering(pc, timeoutMs = ICE_GATHER_TIMEOUT_MS) {
  return new Promise((resolve) => {
    if (pc.iceGatheringState === 'complete') return resolve()
    let done = false
    const finish = () => {
      if (done) return
      done = true
      pc.removeEventListener('icegatheringstatechange', onChange)
      resolve()
    }
    const onChange = () => {
      if (pc.iceGatheringState === 'complete') finish()
    }
    pc.addEventListener('icegatheringstatechange', onChange)
    setTimeout(finish, timeoutMs)
  })
}

function resolveLocation(baseUrl, location) {
  if (!location) return null
  try {
    return new URL(location, baseUrl).toString()
  } catch {
    return null
  }
}

/**
 * 创建一路 WHEP 播放器。
 *
 * @param {object} opts
 * @param {string} opts.url                 完整 WHEP 地址（含 path）
 * @param {(stream: MediaStream) => void} opts.onTrack   拿到媒体流（挂到 <video>）
 * @param {(state: string, detail: string) => void} opts.onState  状态变化
 * @param {(msg: string) => void} [opts.onLog]           诊断日志
 * @returns {{ stop: Function, restart: Function, getState: Function }}
 */
export function createWhepPlayer({
  url,
  onTrack,
  onState = () => {},
  onLog = () => {},
  maxRetries = 2,
}) {
  let pc = null
  let resourceUrl = null
  let stopped = false
  let retries = 0
  let retryTimer = null
  let connectTimer = null
  let currentState = 'idle'

  const setState = (state, detail = '') => {
    currentState = state
    onState(state, detail)
  }

  const clearTimers = () => {
    if (connectTimer) {
      clearTimeout(connectTimer)
      connectTimer = null
    }
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  const teardownPc = () => {
    if (!pc) return
    try {
      pc.ontrack = null
      pc.onicecandidate = null
      pc.onconnectionstatechange = null
      pc.onicegatheringstatechange = null
      pc.close()
    } catch {
      /* 关闭失败无需处理 */
    }
    pc = null
  }

  // 通知服务端释放该路会话（WHEP 用 DELETE 资源 URL）
  const releaseResource = async () => {
    if (!resourceUrl) return
    try {
      await fetch(resourceUrl, { method: 'DELETE', mode: 'cors' })
    } catch {
      /* 忽略：服务端超时会自行回收 */
    }
    resourceUrl = null
  }

  const scheduleRetry = (reason) => {
    if (stopped) return
    retries += 1
    // 重试次数用尽 → 不再自愈，上报 failed 让上层降级到 HLS
    if (retries > maxRetries) {
      setState('failed', `WebRTC 不可用（${reason}，已重试 ${retries - 1} 次）`)
      return
    }
    const delay = Math.min(1000 * 2 ** (retries - 1), RETRY_MAX_DELAY_MS)
    setState('reconnecting', `${reason}；${Math.round(delay / 1000)}s 后重试（第 ${retries} 次）`)
    clearTimers()
    retryTimer = setTimeout(() => {
      retryTimer = null
      connect()
    }, delay)
  }

  const connect = async () => {
    if (stopped) return
    setState(retries ? 'reconnecting' : 'connecting')

    try {
      pc = new RTCPeerConnection({ iceServers: [] })
    } catch (err) {
      onLog(`创建 RTCPeerConnection 失败：${err.message}`)
      setState('failed', '浏览器不支持 WebRTC')
      return
    }

    pc.addTransceiver('video', { direction: 'recvonly' })
    pc.addTransceiver('audio', { direction: 'recvonly' })

    pc.ontrack = (ev) => {
      const stream = ev.streams && ev.streams[0]
      if (stream) onTrack(stream)
    }
    pc.onconnectionstatechange = () => {
      if (!pc) return
      const st = pc.connectionState
      if (st === 'connected') {
        retries = 0
        if (connectTimer) {
          clearTimeout(connectTimer)
          connectTimer = null
        }
        setState('connected', 'WebRTC 已连接')
      } else if (st === 'failed') {
        teardownPc()
        scheduleRetry('连接失败')
      } else if (st === 'disconnected') {
        setState('reconnecting', '连接中断，等待恢复')
      }
    }

    connectTimer = setTimeout(() => {
      if (stopped || currentState === 'connected') return
      onLog('连接超时')
      teardownPc()
      scheduleRetry('连接超时')
    }, CONNECT_TIMEOUT_MS)

    try {
      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      // 非 trickle：等 ICE 收集完成再 POST，兼容性最好（MediaMTX v1.4.2 支持）
      await waitIceGathering(pc)

      const res = await fetch(url, {
        method: 'POST',
        mode: 'cors',
        headers: { 'Content-Type': 'application/sdp' },
        body: pc.localDescription.sdp,
      })
      if (!res.ok) {
        throw new Error(`服务端返回 ${res.status} ${res.statusText || ''}`.trim())
      }
      const answer = await res.text()
      resourceUrl = resolveLocation(url, res.headers.get('Location'))
      await pc.setRemoteDescription({ type: 'answer', sdp: answer })
      onLog('已建立会话，等待媒体流')
    } catch (err) {
      onLog(`WHEP 失败：${err.message}`)
      teardownPc()
      scheduleRetry(err.message)
    }
  }

  const stop = async () => {
    stopped = true
    clearTimers()
    await releaseResource()
    teardownPc()
    setState('stopped')
  }

  const restart = async () => {
    clearTimers()
    await releaseResource()
    teardownPc()
    retries = 0
    stopped = false
    connect()
  }

  return {
    stop,
    restart,
    getState: () => currentState,
    start: connect,
  }
}
