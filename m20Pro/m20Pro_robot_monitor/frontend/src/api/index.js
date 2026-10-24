/**
 * WebSocket 客户端：订阅后端 10Hz 快照。
 *
 * 契约：后端每 100ms 推送一次完整快照（schema_version 见 /api/v1/schema）；
 * 本文件只负责连接/重连/解析，不关心数据来自 UDP 还是 ROS2（PLAN §18）。
 */

const DEFAULT_RECONNECT_MS = 1500

function resolveWsUrl () {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  // 生产（FastAPI 静态托管）与开发（Vite 代理 5173）都走同源
  return `${proto}//${location.host}/ws/state`
}

export function createRobotSocket ({ onSnapshot, onStatus } = {}) {
  let ws = null
  let closedByUser = false
  let timer = null

  function scheduleReconnect () {
    if (closedByUser || timer) return
    timer = setTimeout(() => {
      timer = null
      connect()
    }, DEFAULT_RECONNECT_MS)
  }

  function connect () {
    ws = new WebSocket(resolveWsUrl())
    ws.onopen = () => onStatus && onStatus({ connected: true })
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data)
        onSnapshot && onSnapshot(data)
      } catch (err) {
        console.warn('快照解析失败', err)
      }
    }
    ws.onerror = () => onStatus && onStatus({ connected: false })
    ws.onclose = () => {
      onStatus && onStatus({ connected: false })
      scheduleReconnect()
    }
  }

  return {
    connect,
    close () {
      closedByUser = true
      if (timer) clearTimeout(timer)
      if (ws) ws.close()
    }
  }
}

// ── 终端标识（控制权归属 / 多操作员互斥）──────────────────────────────
// 控制闸在后端是全局单例，同一时刻只有一个 owner。**每个写请求都必须能回答
// "这条指令是哪个终端发的"**，否则会被归属闸拒：NOT_OWNER「未携带终端标识」。
//
// 2026-10-19 真踩：机器人设置面板走 /api/v1/robot/light 这类**独立端点**，
// 只在 useRobotState.js 里带 session_id 覆盖不到 → 单人也报"被占用"。
// 因此标识改由本层统一注入（见 postJson），任何面板都不会漏。
const SESSION_KEY = 'm20-console-session-id'

/** 读取（或首次生成）本终端标识。
 *  与 useRobotState.js 共用同一个 storage key —— 两处若各自生成，
 *  会出现"自己是 owner，却因为带了另一个 id 被自己拒掉"的怪象。 */
export function getSessionId () {
  const gen = () => 'term-' + Math.random().toString(36).slice(2, 10)
  try {
    let sid = sessionStorage.getItem(SESSION_KEY)
    if (!sid) {
      sid = gen()
      sessionStorage.setItem(SESSION_KEY, sid)
    }
    return sid
  } catch (err) {
    return gen()          // 隐私模式 / 禁用 storage 时兜底（刷新会换终端）
  }
}

/** REST 助手：控制指令等写操作。
 *
 *  **自动注入 `session_id`**：调用方不必关心归属（也避免漏带）。
 *  显式传入的 `session_id` 优先（便于测试 / 特殊情况）。
 *  非对象 body（数组 / 字符串）原样发送，不注入。
 */
export async function postJson (path, body = {}) {
  const payload = (body && typeof body === 'object' && !Array.isArray(body))
    ? { session_id: getSessionId(), ...body }
    : body
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return res.json()
}

export async function getJson (path) {
  const res = await fetch(path)
  return res.json()
}
