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

/** REST 助手：控制指令等写操作。 */
export async function postJson (path, body = {}) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  return res.json()
}

export async function getJson (path) {
  const res = await fetch(path)
  return res.json()
}
