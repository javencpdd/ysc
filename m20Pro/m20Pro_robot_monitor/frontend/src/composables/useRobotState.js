import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { createRobotSocket, getJson, postJson } from '../api/index.js'

/**
 * 机器人状态组合式函数：WS 快照 + 新鲜度（stale）+ 控制 API。
 *
 * 新鲜度语义（ADR-006）：**前端永不自己猜新鲜度**，一律用后端快照里的
 * `topics[x].stale` 与 `connected`；停更时顶部红色横幅 + 面板置灰。
 */
export function useRobotState () {
  const snapshot = ref(null)
  const wsConnected = ref(false)
  const control = ref({})
  const socket = ref(null)
  /** 距最后一帧的展示用计时（秒），仅用于横幅文案 */
  const sinceSeconds = ref(0)
  let tick = null
  let leaseTimer = null

  //: 控制租约自动续约间隔。后端 lease_seconds=5s（config.py），
  //: 2s 间隔留 2.5 倍余量（2026-10-15 修复：此前 renewLease 无任何调用方，
  //: 开启控制 5s 后所有指令都会被租约闸拒发 —— 这是历史上 rejected 计数
  //: 悄悄增长的根源，前端表现为"按钮点了没反应"）
  const LEASE_RENEW_MS = 2000

  const topics = computed(() => (snapshot.value && snapshot.value.topics) || {})
  const connected = computed(() => !!(snapshot.value && snapshot.value.connected))
  const staleTopics = computed(() =>
    Object.keys(topics.value).filter((k) => topics.value[k] && topics.value[k].stale)
  )
  const degraded = computed(() => !connected.value || staleTopics.value.length > 0)

  function topic (name) {
    const t = topics.value[name]
    return (t && t.data) || {}
  }
  function isStale (name) {
    const t = topics.value[name]
    return t ? !!t.stale : true
  }

  onMounted(() => {
    socket.value = createRobotSocket({
      onSnapshot: (data) => {
        snapshot.value = data
        sinceSeconds.value = 0
      },
      onStatus: (s) => { wsConnected.value = !!s.connected }
    })
    socket.value.connect()
    // 横幅计时（页面本地估算，仅用于文案；判定仍以后端 stale 为准）
    tick = setInterval(() => { sinceSeconds.value += 0.5 }, 500)
    refreshControl()
    // 租约自动续约：仅当控制已开启时续约（未开启时无意义；
    // WS 断开后后端清租约，重连续约会自动恢复，无需额外处理）
    leaseTimer = setInterval(() => {
      const c = control.value || {}
      if (!c.enabled) return
      renewLease().catch(() => { /* 网络抖动忽略，下一轮再试 */ })
    }, LEASE_RENEW_MS)
  })

  onUnmounted(() => {
    if (tick) clearInterval(tick)
    if (leaseTimer) clearInterval(leaseTimer)
    if (socket.value) socket.value.close()
  })

  // ---------------------------------------------------------------- 控制
  async function refreshControl () {
    try {
      const res = await getJson('/api/v1/control/status')
      control.value = res.control || {}
    } catch (err) {
      console.warn('读取控制状态失败', err)
    }
  }

  async function enableControl () {
    const res = await postJson('/api/v1/control/enable', { enable: true, confirmed: true })
    await refreshControl()
    return res
  }
  async function disableControl () {
    const res = await postJson('/api/v1/control/enable', { enable: false, confirmed: true })
    await refreshControl()
    return res
  }
  async function renewLease () {
    return postJson('/api/v1/control/lease')
  }
  async function sendCommand (name, params = {}, confirmed = true) {
    const res = await postJson('/api/v1/control/command', { name, params, confirmed })
    await refreshControl()
    return res
  }
  async function sendAxis (values, continuous = false) {
    return postJson('/api/v1/control/axis', { ...values, continuous })
  }
  async function stopAxis () {
    return postJson('/api/v1/control/axis/stop')
  }
  async function estop () {
    const res = await postJson('/api/v1/control/estop')
    await refreshControl()
    return res
  }
  async function clearEstop () {
    const res = await postJson('/api/v1/control/estop/clear')
    await refreshControl()
    return res
  }

  return {
    snapshot, topics, connected, wsConnected, degraded, staleTopics, sinceSeconds,
    control, topic, isStale,
    enableControl, disableControl, renewLease, sendCommand, sendAxis, stopAxis,
    estop, clearEstop, refreshControl
  }
}
