/**
 * 后端接口封装层。
 *
 * 约定：
 * - REST 走同源 /api（Vite dev 由 proxy 转发到后端 8000 端口）；
 * - WebSocket 走 /ws/state，由服务端以 10Hz 主动推送；
 * - 若设置环境变量 VITE_BACKEND_URL，则直接跨域访问后端，方便单端口/分离部署。
 */

const BACKEND = import.meta.env.VITE_BACKEND_URL || ''

/** REST 基础地址 */
export const apiBase = BACKEND

/** WebSocket 基础地址 */
export const wsBase = BACKEND ? BACKEND.replace(/^http/, 'ws') : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`

/** GET 请求封装，统一错误处理 */
async function httpGet(path, params = {}) {
  const url = new URL(`${apiBase}${path}`, location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, v)
  })
  const resp = await fetch(url.toString())
  if (!resp.ok) {
    throw new Error(`${path} 请求失败: HTTP ${resp.status}`)
  }
  return resp.json()
}

/** 获取当前状态快照 */
export function fetchState() {
  return httpGet('/api/state')
}

/** 获取服务与链路状态 */
export function fetchStatus() {
  return httpGet('/api/status')
}

/** 获取最近 N 条原始报文 */
export function fetchRaw(limit = 20) {
  return httpGet('/api/raw', { limit })
}

/** 清空原始报文缓存 */
export async function clearRaw() {
  const url = new URL(`${apiBase}/api/raw/clear`, location.origin)
  const resp = await fetch(url.toString(), { method: 'POST' })
  if (!resp.ok) throw new Error(`清空失败: HTTP ${resp.status}`)
  return resp.json()
}

/** POST JSON 请求封装，统一错误处理 */
async function httpPost(path, body) {
  const url = new URL(`${apiBase}${path}`, location.origin)
  const resp = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new Error(data.detail || `${path} 请求失败: HTTP ${resp.status}`)
  }
  return data
}

// ----------------------------------------------------------------------
// 控制通道接口（写方向）
// 注意：这些接口会直接向运动主机下发指令，调用前务必确认机器人状态
// ----------------------------------------------------------------------

/** 获取控制服务状态 */
export function fetchControlStatus() {
  return httpGet('/api/control/status')
}

/** 获取预置指令列表（verified=false 的为待确认占位值） */
export function fetchControlPresets() {
  return httpGet('/api/control/presets')
}

/** 启用控制通道 */
export function enableControl() {
  return httpPost('/api/control/enable')
}

/** 停用控制通道（停心跳 + 零速 + 释放 socket） */
export function disableControl() {
  return httpPost('/api/control/disable')
}

/** 下发速度指令 */
export function sendVelocity(x, y, yaw) {
  return httpPost('/api/control/velocity', { x, y, yaw })
}

/** 下发预置指令 */
export function sendPreset(name) {
  return httpPost('/api/control/preset', { name })
}

/** 下发自定义指令报文 */
export function sendCustom(cmdCode, cmdValue, type, data) {
  return httpPost('/api/control/custom', {
    cmd_code: cmdCode,
    cmd_value: cmdValue,
    type,
    data: data === null || data === '' ? null : Number(data)
  })
}

/** 下发原始十六进制报文 */
export function sendRawHex(hex) {
  return httpPost('/api/control/raw', { hex })
}

/** 停止移动（零速） */
export function stopMotion() {
  return httpPost('/api/control/stop')
}

/** 急停 */
export function emergencyStop() {
  return httpPost('/api/control/estop')
}

/** 解除急停 */
export function clearEstop() {
  return httpPost('/api/control/estop/clear')
}

/** 开启心跳 */
export function startHeartbeat() {
  return httpPost('/api/control/heartbeat/start')
}

/** 停止心跳 */
export function stopHeartbeat() {
  return httpPost('/api/control/heartbeat/stop')
}

/** 续约心跳租约 */
export function renewHeartbeat() {
  return httpPost('/api/control/heartbeat/renew')
}

/** 获取指令审计记录 */
export function fetchControlAudit(limit = 50) {
  return httpGet('/api/control/audit', { limit })
}

// ----------------------------------------------------------------------
// 数据源模式切换（状态监听：ROS 话题订阅 / sniff 旁路抓包）
// ----------------------------------------------------------------------

/** 获取当前 / 配置的数据源模式 */
export function fetchSource() {
  return httpGet('/api/source')
}

/** 运行时切换数据源模式：ros / sniff / bind / auto */
export function setSource(mode) {
  return httpPost(`/api/source/set?mode=${encodeURIComponent(mode)}`)
}

/**
 * 状态 WebSocket 客户端。
 *
 * 负责：
 * - 建立连接、断线自动重连（指数退避上限 5s）；
 * - 把服务端快照分发给回调；
 * - 维护 UI 侧的链路状态（connecting / open / closed）。
 */
export class StateSocket {
  /**
   * @param {Object} options
   * @param {(snapshot: any) => void} options.onSnapshot 收到快照时的回调
   * @param {(state: 'connecting'|'open'|'closed', detail?: string) => void} options.onStatus 连接状态变化回调
   * @param {number} options.retryInterval 重连基础间隔（毫秒）
   */
  constructor({ onSnapshot, onStatus, retryInterval = 1500 }) {
    this.onSnapshot = onSnapshot
    this.onStatus = onStatus
    this.retryInterval = retryInterval
    this.socket = null
    this.retryTimer = null
    this.retryCount = 0
    this.manualClosed = false
  }

  /** 建立连接（若已连接则忽略） */
  connect() {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return
    }
    this.manualClosed = false
    this.onStatus?.('connecting')

    const ws = new WebSocket(`${wsBase}/ws/state`)
    this.socket = ws

    ws.onopen = () => {
      this.retryCount = 0
      this.onStatus?.('open')
    }

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        this.onSnapshot?.(payload)
      } catch (err) {
        console.error('[StateSocket] 快照解析失败', err)
      }
    }

    ws.onerror = () => {
      // 具体的错误信息浏览器不暴露，统一按断连处理
      this.onStatus?.('closed', '连接异常')
    }

    ws.onclose = () => {
      this.onStatus?.('closed')
      if (!this.manualClosed) this._scheduleRetry()
    }
  }

  /** 安排一次重连（退避策略） */
  _scheduleRetry() {
    if (this.retryTimer) return
    const delay = Math.min(this.retryInterval * Math.pow(1.5, this.retryCount), 5000)
    this.retryCount += 1
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null
      this.connect()
    }, delay)
  }

  /** 主动请求一次即时快照（服务端收到任意文本即回推一帧） */
  ping() {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send('ping')
    }
  }

  /** 关闭连接并停止重连 */
  close() {
    this.manualClosed = true
    if (this.retryTimer) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    if (this.socket) {
      this.socket.close()
      this.socket = null
    }
  }
}
