import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { createRobotSocket, getJson, getSessionId, postJson } from '../api/index.js'

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
  //: 看门狗状态（含定时移动倒计时；2026-10-16 加）
  const watchdog = ref({})
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

  // ── 终端标识（控制权归属 / 多操作员互斥，2026-10-19 加）────────────
  // 控制闸在后端是**全局单例**：多个浏览器连的是同一个服务、同一把开关。
  // 改造前"谁最后点谁说了算"——A 正遥控时 B 点停止就把 A 掐断，且 A、B 可以
  // 同时开启、同时往一条狗发运动指令。现在每个终端生成自己的 session_id，
  // 申请控制权时登记为 owner，同一时刻只有一个 owner，其余终端只读。
  //
  // 存 sessionStorage：本标签页刷新后仍是同一终端（不会把自己挤下去），
  // 新标签页算新终端（可并存，但只有一个拿得到控制权）。
  // 标识由 api 层统一生成/读取（postJson 也会自动注入同一个），
  // 这里只取一份用于"这条归属是不是我"的比对，避免两处各生成一份。
  const sessionId = getSessionId()
  /** 终端可读名：在别的终端上会显示"当前由「xxx」控制" */
  const terminalLabel = '终端 ' + sessionId.slice(-4)

  // 控制权归属展示：owner 信息由后端给（快照含 control.owner），前端只比对。
  // 后端对外只给 session 前 8 位短码，比对时用同样规则切片。
  const controlOwner = computed(() => control.value.owner || { held: false })
  /** 本终端能否驱动机器人。
   *  ⚠️ **无主模式（held=false）必须算"可以"** —— 那是单机 / 老后端 /
   *  本机脚本直接 enable 的情形，此时控制闸没有归属约束，任何人都能操作。
   *  若在此返回 false，单机场景下所有按钮会被误禁用（真实回归风险）。 */
  const isControlOwner = computed(() => {
    if (!controlOwner.value.held) return true
    return controlOwner.value.session === sessionId.slice(0, 8)
  })

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
      watchdog.value = res.watchdog || {}
    } catch (err) {
      console.warn('读取控制状态失败', err)
    }
  }

  /** 申请控制权（多操作员互斥的核心入口）。
   *  - 无人占用 → 成为 owner；自己已占用 → 幂等续期；
   *  - 他人占用 → ok=false / reason='CONTROL_HELD'，res.owner 为占用者信息，
   *    前端据此提示"是否接管"，用户确认后以 force=true 重调本函数。
   *  force=true 属危险动作（会把对方踢下线），必须经前端二次确认。 */
  async function enableControl (force = false) {
    const res = await postJson('/api/v1/control/acquire', {
      session_id: sessionId, label: terminalLabel, force, confirmed: true
    })
    await refreshControl()
    return res
  }
  async function disableControl () {
    const res = await postJson('/api/v1/control/release', {
      session_id: sessionId, confirmed: true
    })
    await refreshControl()
    return res
  }
  async function renewLease () {
    return postJson('/api/v1/control/lease', { session_id: sessionId })
  }
  /** 暂停 / 恢复心跳（2026-10-16 加，遥测让渡）。
   *  paused=true 需 confirmed=true（停心跳 = 放弃遥视，车可能仍在动）；
   *  paused=false（恢复视野）是安全动作，不需确认。
   *  暂停期间驱动类指令会被服务端闸拒绝（TELEMETRY_PAUSED），软急停除外。 */
  async function sendHeartbeat (paused, confirmed = false) {
    const res = await postJson('/api/v1/link/heartbeat', { paused, confirmed })
    await refreshControl()
    return res
  }
  async function sendCommand (name, params = {}, confirmed = true) {
    const res = await postJson('/api/v1/control/command',
      { name, params, confirmed, session_id: sessionId })
    await refreshControl()
    return res
  }
  async function sendAxis (values, continuous = false, channel = 'steer') {
    return postJson('/api/v1/control/axis',
      { ...values, continuous, channel, session_id: sessionId })
  }
  /** 定时移动（2026-10-16 加）：后端计时 durationS 秒后自动零位停止。
   *  channel: 'steer'（2/21 主通道）| 'real'（2/25 实时通道） */
  async function sendTimedAxis (values, durationS, channel = 'steer') {
    const res = await postJson('/api/v1/control/axis/timed',
      { ...values, duration_s: durationS, channel, session_id: sessionId })
    await refreshControl()
    return res
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
    control, watchdog, topic, isStale,
    // 控制权归属（多操作员互斥）
    sessionId, terminalLabel, controlOwner, isControlOwner,
    enableControl, disableControl, renewLease, sendCommand, sendAxis, sendTimedAxis,
    stopAxis, estop, clearEstop, refreshControl, sendHeartbeat
  }
}
