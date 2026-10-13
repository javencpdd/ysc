<script setup>
/**
 * ControlPanel.vue
 * 远程控制面板：按厂商文档《运动主机 UDP 通讯接口》1.2 节的指令集实现。
 *
 * 安全设计：
 * 1. 控制通道默认关闭，必须显式启用；
 * 2. 心跳开启后由定时器定期续约；只有「用户主动停止 / 停用通道 / 急停 / 离开页面」
 *    才会终止，切换页面标签等组件级行为不影响心跳（后端另有租约兜底）；
 * 3. 高风险动作（后空翻/向前跳/扭身跳等）二次确认后才下发。
 */
import { ref, shallowRef, computed, onMounted, onUnmounted } from 'vue'
import {
  fetchControlStatus,
  fetchControlPresets,
  enableControl,
  disableControl,
  sendVelocity,
  sendPreset,
  sendCustom,
  sendRawHex,
  stopMotion,
  emergencyStop,
  clearEstop,
  startHeartbeat,
  stopHeartbeat,
  renewHeartbeat,
  fetchSource,
  setSource
} from '../api/index.js'

/** 速度各轴的取值范围与步长（文档 1.2.12；后端会二次限幅） */
const LIMITS = {
  x: { min: -1, max: 1, step: 0.05, label: '前后', unit: 'm/s', hint: '正值前进' },
  y: { min: -0.5, max: 0.5, step: 0.05, label: '左右', unit: 'm/s', hint: '正值向右' },
  yaw: { min: -1.5, max: 1.5, step: 0.05, label: '旋转', unit: 'rad/s', hint: '正值向右转' }
}
const VEL_AXES = ['x', 'y', 'yaw']

/** 指令分组展示顺序：少量指令 → 状态 → 步态 → 动作与 AI */
const GROUP_ORDER = ['模式', '其他', '状态', '步态', '动作', 'AI']
/** 数量较少的常用指令，合并到同一张卡片里 */
const QUICK_GROUPS = ['模式', '其他']

/** 控制服务状态 */
const status = shallowRef(null)
/** 预置指令列表 */
const presets = ref([])
/** 速度输入（文档语义：x 正=前进，y 正=向右，yaw 正=向右转） */
const vel = ref({ x: 0, y: 0, yaw: 0 })
/** 自定义指令表单：三个头字段一律按十六进制输入，与报文原文一致 */
const custom = ref({ code: '0x21040001', value: '0x00000000', type: '0x00000000', data: 0.0 })
/** 原始十六进制报文 */
const rawHex = ref('')
/** 最近一次发送结果 */
const lastResult = ref(null)
/** 操作提示 */
const notice = ref(null)
/** 待确认的危险指令 */
const pendingDanger = ref(null)
/** 数据源（监听）模式：ros / sniff / bind / auto */
const sourceMode = ref('')
const sourceConfigured = ref('')
const sourceBusy = ref(false)
/** 数据源自检结果（来自 /api/source 的 diag 字段） */
const sourceDiag = ref(null)

/** 自检结论文案 */
const VERDICT_TEXT = { ok: '正常', warn: '需注意', fail: '异常', wait: '等待数据中' }

// ---------------------------------------------------------------- 心跳
/** 用户是否希望心跳保持开启（只有主动停止/停用/急停/离开页面才置 false） */
const hbDesired = ref(false)
/** 最近一次成功续约时间（本地 ms） */
const hbLastBeatAt = ref(0)
/** 累计续约次数 */
const hbBeatCount = ref(0)
/** 正在自动恢复中（避免并发重复拉起） */
const hbRestarting = ref(false)
/** 每秒滴答，用于显示"多久之前续约" */
const nowTick = ref(Date.now())

let renewTimer = null
let renewIntervalMs = 0
let statusTimer = null
let sourceTimer = null
let hbWatchdogTimer = null

const enabled = computed(() => Boolean(status.value?.enabled))
const estop = computed(() => Boolean(status.value?.estop))
const hbRunning = computed(() => Boolean(status.value?.heartbeat_running))

/**
 * 当前模式回显（协议不主动上报这些状态，只能以「本进程最后一次成功下发的模式指令」近似）。
 * 后端 last_modes: { 控制模式: {name, code_hex, ts}, 运动模式: {...}, 持续运动: {...}, 'AI 状态': {...} }
 */
const MODE_CATEGORIES = ['控制模式', '运动模式', '持续运动', 'AI 状态']
const modeChips = computed(() => {
  const lm = status.value?.last_modes || {}
  return MODE_CATEGORIES.map((cat) => {
    const rec = lm[cat]
    return {
      cat,
      name: rec ? rec.name : null,
      ts: rec ? rec.ts : null,
    }
  })
})
const hasAnyMode = computed(() => modeChips.value.some((m) => m.name))

/** 时间戳转 HH:MM:SS */
function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 指令按 group 归类，保持后端返回顺序 */
const grouped = computed(() => {
  const map = new Map()
  for (const cmd of presets.value) {
    if (!map.has(cmd.group)) map.set(cmd.group, [])
    map.get(cmd.group).push(cmd)
  }
  return Array.from(map.entries()).map(([group, items]) => ({ group, items }))
})

/** 按 GROUP_ORDER 排序；未列出的分组排在最后 */
const orderedGroups = computed(() => {
  const rank = (g) => {
    const i = GROUP_ORDER.indexOf(g)
    return i < 0 ? 999 : i
  }
  return grouped.value.slice().sort((a, b) => rank(a.group) - rank(b.group))
})

/** group -> items 快速查找 */
const groupMap = computed(() => {
  const m = {}
  for (const g of grouped.value) m[g.group] = g.items
  return m
})

/** 常用（少量）指令分组 */
const quickGroups = computed(() =>
  QUICK_GROUPS.filter((g) => groupMap.value[g]?.length).map((g) => ({
    group: g,
    items: groupMap.value[g]
  }))
)

/** 已按名称显式渲染的分组之外，剩余未列出的分组（兜底，防止后端新增分组被遗漏） */
const restGroups = computed(() =>
  orderedGroups.value.filter((g) => !QUICK_GROUPS.includes(g.group) && g.group !== '状态' && g.group !== '步态' && g.group !== '动作' && g.group !== 'AI')
)

/** 心跳状态文案 */
const hbSinceText = computed(() => {
  if (!hbRunning.value || !hbLastBeatAt.value) return ''
  const s = Math.max(0, Math.round((nowTick.value - hbLastBeatAt.value) / 1000))
  return `${s}s 前续约`
})

function setNotice(text, ok = true) {
  notice.value = { text, ok }
  setTimeout(() => {
    if (notice.value?.text === text) notice.value = null
  }, 3000)
}

async function run(fn, successText) {
  try {
    const result = await fn()
    lastResult.value = result
    if (successText) setNotice(successText, true)
    await refreshStatus()
    return result
  } catch (err) {
    setNotice(err.message || '操作失败', false)
    return null
  }
}

async function refreshStatus() {
  try {
    status.value = await fetchControlStatus()
  } catch (err) {
    console.warn('[ControlPanel] 获取控制状态失败', err)
  }
}

async function refreshPresets() {
  try {
    const data = await fetchControlPresets()
    presets.value = data.commands || []
  } catch (err) {
    console.warn('[ControlPanel] 获取指令表失败', err)
  }
}

// ---------------------------------------------------------------- 数据源模式
async function refreshSource() {
  try {
    const d = await fetchSource()
    sourceMode.value = d.mode || ''
    sourceConfigured.value = d.configured || ''
    sourceDiag.value = d.diag || null
  } catch (err) {
    console.warn('[ControlPanel] 获取数据源模式失败', err)
  }
}

async function onSetSource(mode) {
  sourceBusy.value = true
  try {
    const r = await setSource(mode)
    if (r?.ok) {
      sourceMode.value = r.mode || mode
      setNotice(`已切换监听模式：${r.mode}`)
    } else {
      setNotice(r?.detail || '切换失败', false)
    }
  } catch (err) {
    setNotice(err.message || '切换失败', false)
  } finally {
    sourceBusy.value = false
  }
}

// ---------------------------------------------------------------- 心跳
function stopRenewTimer() {
  if (renewTimer) {
    clearInterval(renewTimer)
    renewTimer = null
  }
  renewIntervalMs = 0
}

/**
 * 确保续约定时器存在。
 * 关键点：周期一致时**不重建**——否则每次状态刷新都 clear/create，
 * 会造成续约节奏抖动甚至丢失，表现就是"心跳会自己停"。
 */
function ensureRenewTimer() {
  const lease = Number(status.value?.heartbeat_lease) || 5
  const interval = Math.max(1000, Math.round((lease * 1000) / 3))
  if (renewTimer && renewIntervalMs === interval) return
  stopRenewTimer()
  renewIntervalMs = interval
  renewTimer = setInterval(() => {
    void doRenew()
  }, interval)
}

async function doRenew() {
  try {
    await renewHeartbeat()
    hbLastBeatAt.value = Date.now()
    hbBeatCount.value += 1
  } catch (err) {
    console.warn('[ControlPanel] 心跳续约失败', err)
  }
}

/** 后端心跳意外停止时自动拉起（用户并未要求停止） */
async function restartHeartbeat() {
  if (hbRestarting.value) return
  hbRestarting.value = true
  try {
    await startHeartbeat()
    await refreshStatus()
    if (hbRunning.value) {
      hbLastBeatAt.value = Date.now()
      ensureRenewTimer()
    }
  } catch (err) {
    console.warn('[ControlPanel] 心跳自动恢复失败', err)
  } finally {
    hbRestarting.value = false
  }
}

/**
 * 心跳看门狗（每秒）：把"是否续约"交给状态驱动，而不是只在点击那一刻决定一次。
 * 这样即使某次状态刷新失败、或后端租约意外到期，也能自愈。
 */
function hbWatchdog() {
  nowTick.value = Date.now()
  if (!hbDesired.value || !enabled.value || estop.value) {
    stopRenewTimer()
    return
  }
  if (!hbRunning.value) {
    void restartHeartbeat()
    return
  }
  ensureRenewTimer()
}

async function onStartHeartbeat() {
  hbDesired.value = true
  await run(startHeartbeat, '心跳已开启')
  if (hbRunning.value) {
    hbLastBeatAt.value = Date.now()
    ensureRenewTimer()
  }
}

async function onStopHeartbeat() {
  hbDesired.value = false
  stopRenewTimer()
  await run(stopHeartbeat, '心跳已停止')
}

function handleBeforeUnload() {
  hbDesired.value = false
  stopRenewTimer()
  if (hbRunning.value) {
    const url = new URL('/api/control/heartbeat/stop', location.origin)
    navigator.sendBeacon?.(url.toString())
    try {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', url.toString(), false)
      xhr.send()
    } catch (err) {
      /* 忽略：后端有租约兜底 */
    }
  }
}

// ---------------------------------------------------------------- 操作
async function onEnable() {
  await run(enableControl, '控制通道已启用，请确认机器人周围安全')
}

async function onDisable() {
  hbDesired.value = false
  stopRenewTimer()
  await run(disableControl, '控制通道已停用')
}

/** 点击指令按钮：危险动作需二次确认 */
async function onPreset(cmd) {
  if (cmd.danger) {
    pendingDanger.value = cmd
    return
  }
  await doPreset(cmd)
}

async function doPreset(cmd) {
  pendingDanger.value = null
  await run(() => sendPreset(cmd.name), `已下发：${cmd.name}`)
}

function cancelDanger() {
  pendingDanger.value = null
}

// ---------------------------------------------------------------- 速度
/** 限定范围并对齐步长；非法值返回 null（由调用方决定是否回退） */
function clampVel(v, min, max, step) {
  if (typeof v !== 'number' || !Number.isFinite(v)) return null
  const snapped = Math.round(v / step) * step
  const c = Math.min(max, Math.max(min, snapped))
  return Number(c.toFixed(4))
}

function setVel(axis, v) {
  const lim = LIMITS[axis]
  const c = clampVel(v, lim.min, lim.max, lim.step)
  if (c === null) return
  vel.value = { ...vel.value, [axis]: c }
}

/** 文本框显示值（随滑块/摇杆/归零实时同步） */
const velText = computed(() => ({
  x: vel.value.x.toFixed(2),
  y: vel.value.y.toFixed(2),
  yaw: vel.value.yaw.toFixed(2)
}))

/** 输入中：合法则写入模型（滑块与摇杆随之更新）；非法则不动模型 */
function onVelInput(axis, ev) {
  const raw = ev.target.value
  // 允许中间输入状态（空、"-"、"." 等），不打断用户键入
  if (raw === '' || raw === '-' || raw === '.' || raw === '-.') return
  setVel(axis, Number(raw))
}

/** 失焦/回车：内容非法或为空时回退到上一次有效值 */
function onVelCommit(axis, ev) {
  ev.target.value = velText.value[axis]
}

async function onSendVelocity() {
  await run(() => sendVelocity(vel.value.x, vel.value.y, vel.value.yaw), '速度指令已下发')
}

/** 速度归零：三项全部置 0，滑块与文本框随之刷新 */
async function onZeroVelocity() {
  vel.value = { x: 0, y: 0, yaw: 0 }
  await run(() => sendVelocity(0, 0, 0), '速度已归零')
}

async function onStop() {
  vel.value = { x: 0, y: 0, yaw: 0 }
  await run(stopMotion, '已下发零速')
}

async function onEstop() {
  hbDesired.value = false
  stopRenewTimer()
  await run(emergencyStop, '急停已执行（含厂商软急停指令）')
}

async function onClearEstop() {
  await run(clearEstop, '急停已解除')
}

// ---------------------------------------------------------------- 摇杆
/** 摇杆水平轴：'xy'=左右平移，'xyaw'=转向 */
const joyMode = ref('xy')
/** 拖动摇杆时实时下发速度（遥控模式默认开启，松手会自动发零速） */
const joyLive = ref(true)
const joyEl = ref(null)
const joyActive = ref(false)
/** 摇杆行程半径（px），与 CSS 中 .joy 尺寸配套 */
const JOY_R = 56
let joyLastSend = 0

const joyAxes = computed(() => (joyMode.value === 'xy' ? { v: 'x', h: 'y' } : { v: 'x', h: 'yaw' }))

/** 摇杆手柄位置由 vel 反推 —— 与滑块、文本框双向同步 */
const knobStyle = computed(() => {
  const { v, h } = joyAxes.value
  const vv = vel.value[v] / LIMITS[v].max
  const hv = vel.value[h] / LIMITS[h].max
  return {
    left: `calc(50% + ${(hv * JOY_R).toFixed(1)}px)`,
    top: `calc(50% + ${(-vv * JOY_R).toFixed(1)}px)`
  }
})

function joyFromPoint(clientX, clientY) {
  const el = joyEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  const r = Math.min(rect.width, rect.height) / 2
  let dx = (clientX - cx) / r
  let dy = (clientY - cy) / r
  // 限制在单位圆内
  const len = Math.hypot(dx, dy)
  if (len > 1) {
    dx /= len
    dy /= len
  }
  const { v, h } = joyAxes.value
  // 屏幕 y 向下为正；前后轴正值=前进 => 向上推对应 -dy
  setVel(v, -dy * LIMITS[v].max)
  setVel(h, dx * LIMITS[h].max)
  if (joyLive.value) sendVelLive()
}

/** 实时下发节流到 ~10Hz，避免拖动时刷爆链路 */
function sendVelLive() {
  const now = Date.now()
  if (now - joyLastSend < 100) return
  joyLastSend = now
  sendVelocity(vel.value.x, vel.value.y, vel.value.yaw).catch((err) => {
    console.warn('[ControlPanel] 摇杆实时下发失败', err)
  })
}

function onJoyDown(ev) {
  joyActive.value = true
  ev.currentTarget.setPointerCapture?.(ev.pointerId)
  joyFromPoint(ev.clientX, ev.clientY)
}

function onJoyMove(ev) {
  if (!joyActive.value) return
  joyFromPoint(ev.clientX, ev.clientY)
}

function onJoyUp() {
  if (!joyActive.value) return
  joyActive.value = false
  // 松手回中：把摇杆当前控制的两个轴归零（不改动另一轴）
  const { v, h } = joyAxes.value
  vel.value = { ...vel.value, [v]: 0, [h]: 0 }
  if (joyLive.value) {
    joyLastSend = 0
    sendVelLive()
  }
}

/** 切换摇杆水平轴时，把上一模式遗留的水平轴清掉，避免残留速度 */
function onJoyModeChange(mode) {
  const prevH = joyAxes.value.h
  joyMode.value = mode
  const nextH = joyAxes.value.h
  if (prevH !== nextH) vel.value = { ...vel.value, [prevH]: 0 }
}

/** 32 位值 -> 0xXXXXXXXX（回显统一用十六进制） */
function hex32(v) {
  if (v === undefined || v === null || v === '') return '—'
  return '0x' + (Number(v) >>> 0).toString(16).toUpperCase().padStart(8, '0')
}

/** 十六进制串 -> uint32；支持 0x 前缀、空格/下划线分隔；非法返回 null */
function parseHex32(s) {
  const t = String(s ?? '').trim().replace(/^0[xX]/, '').replace(/[\s_,]/g, '')
  if (!t) return null
  if (!/^[0-9a-fA-F]{1,8}$/.test(t)) return null
  return parseInt(t, 16) >>> 0
}

async function onSendCustom() {
  const code = parseHex32(custom.value.code)
  if (code === null) {
    setNotice('code 需为十六进制（1~8 位），如 0x21040001', false)
    return
  }
  const value = parseHex32(custom.value.value)
  if (value === null) {
    setNotice('指令值需为十六进制（1~8 位），无有效值时填 0x00000000', false)
    return
  }
  const type = parseHex32(custom.value.type)
  if (type === null) {
    setNotice('type 需为十六进制：0x00000000 简单 / 0x00000001 复杂', false)
    return
  }
  await run(() => sendCustom(code, value, type, custom.value.data), '自定义指令已下发')
}

async function onSendRaw() {
  await run(() => sendRawHex(rawHex.value), '原始报文已下发')
}

/** 把最近一次报文格式化为可读文本 */
const lastPacketText = computed(() => {
  const p = lastResult.value?.packet
  if (!p) return ''
  // 全部按十六进制回显：与报文原文逐字节对应，不做十进制换算
  const head = `${p.kind}(${p.length}B)  code=${p.code_hex}  paramters_size=${hex32(p.paramters_size)}  type=${hex32(p.type)}`
  if (p.data_hex) return `${head}  data=0x${p.data_hex.toUpperCase()}`
  return head
})

onMounted(async () => {
  await refreshPresets()
  await refreshStatus()
  await refreshSource()
  statusTimer = setInterval(refreshStatus, 2000)
  sourceTimer = setInterval(refreshSource, 5000)
  // 心跳看门狗：由状态驱动续约与自愈，不依赖"点击那一次"
  hbWatchdogTimer = setInterval(hbWatchdog, 1000)
  window.addEventListener('beforeunload', handleBeforeUnload)
})

onUnmounted(() => {
  stopRenewTimer()
  clearInterval(statusTimer)
  clearInterval(sourceTimer)
  clearInterval(hbWatchdogTimer)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  // 注意：卸载（例如切换到「监控页面」标签）**不再**主动停止后端心跳。
  // 心跳只因用户主动停止 / 停用通道 / 急停 / 离开页面而终止；
  // 真需要终止时后端还有租约兜底（前端消失超过租约自动停心跳并发零速）。
})
</script>

<template>
  <section class="card">
    <div class="card-title">
      <span>Robot Control</span>
      <span class="sub">{{ status?.target || '--' }}</span>
    </div>

    <!-- 监听模式切换：ROS 话题订阅 / sniff 旁路抓包 -->
    <div class="block source-block">
      <div class="block-title">
        监听模式<small>ROS 话题订阅 / sniff 旁路抓包（运行时可切换）</small>
      </div>
      <div class="row">
        <button class="btn" :class="{ primary: sourceMode === 'ros' }" :disabled="sourceBusy" @click="onSetSource('ros')">ROS 话题订阅</button>
        <button class="btn" :class="{ primary: sourceMode === 'sniff' }" :disabled="sourceBusy" @click="onSetSource('sniff')">sniff 旁路抓包</button>
        <button
          class="btn"
          :class="{ primary: sourceMode === 'auto' }"
          :disabled="sourceBusy"
          @click="onSetSource('auto')"
        >自动(优先ROS)</button>
        <span class="status-pill" :class="sourceMode === 'ros' ? 'on' : 'off'">{{ sourceMode || '—' }}</span>
      </div>
      <div class="hint">
        配置默认：<b>{{ sourceConfigured || 'auto' }}</b>。ROS 模式订阅 transfer_ros2 发布的
        /leg_odom2、/imu/data 等话题（经 ros_bridge_node 转发），不占用 43897 端口；
        sniff 模式直接旁路抓包 43897，需 CAP_NET_RAW。
      </div>

      <!-- 数据源自检：逐项给出可执行的排查结论 -->
      <div v-if="sourceDiag" class="diag" :class="sourceDiag.verdict">
        <div class="diag-head">
          自检结论：<b>{{ VERDICT_TEXT[sourceDiag.verdict] || sourceDiag.verdict }}</b>
          <span class="dim">已收 {{ sourceDiag.frames_received }} 帧</span>
        </div>
        <ul class="diag-list">
          <li v-for="(c, i) in sourceDiag.checks" :key="i">
            <span class="tick" :class="c.ok ? 'ok' : 'no'">{{ c.ok ? '✓' : '✕' }}</span>
            <b>{{ c.item }}</b>
            <span class="dim">{{ c.detail }}</span>
          </li>
        </ul>
        <div class="diag-hint">{{ sourceDiag.hint }}</div>
      </div>
    </div>

    <div class="alert" :class="!enabled ? 'muted' : 'danger'">
      <template v-if="!enabled">
        控制通道<b>已停用</b>。启用后将按厂商文档向运动主机 43893 下发指令，
        <b>不经过 VOA 安全层</b>，请确保机器人周围无人员与障碍物。
      </template>
      <template v-else-if="estop">
        <b>急停锁定中</b>：所有指令已被拒绝，确认安全后可解除。
      </template>
      <template v-else>
        控制通道<b class="live">已启用</b>。速度指令需机器人处于<b>自主模式</b>（见下方常用指令）才会响应。
      </template>
    </div>

    <!-- 通道开关 -->
    <div class="row">
      <button v-if="!enabled" class="btn primary" @click="onEnable">启用控制通道</button>
      <button v-else class="btn" @click="onDisable">停用控制通道</button>
      <button class="btn ghost" :disabled="!enabled" @click="onStop">停止移动（零速）</button>
      <button class="btn danger" :disabled="!enabled || estop" @click="onEstop">急 停</button>
      <button v-if="estop" class="btn warn" @click="onClearEstop">解除急停</button>
    </div>

    <!-- 发包统计：心跳与业务分开累计（后端按 note 分别累加，不受缓冲上限影响） -->
    <div class="sent-stats">
      <span class="stat">累计发送 <b>{{ status?.sent_packets ?? 0 }}</b></span>
      <span class="stat hb">心跳 <b>{{ status?.heartbeat_packets ?? 0 }}</b></span>
      <span class="stat biz">业务 <b>{{ status?.business_packets ?? 0 }}</b></span>
      <span class="stat fail">失败 <b>{{ status?.failed_packets ?? 0 }}</b></span>
    </div>

    <!-- 当前模式回显：协议不上报这些状态，以本服务最后一次成功下发的模式指令近似 -->
    <div class="mode-strip">
      <span class="mode-label">当前模式</span>
      <template v-if="hasAnyMode">
        <span
          v-for="m in modeChips"
          :key="m.cat"
          class="mode-chip"
          :class="{ empty: !m.name }"
          :title="m.ts ? `下发于 ${fmtTime(m.ts)}` : '本服务启动后尚未下发过该类指令'"
        >
          {{ m.cat }}：<b>{{ m.name || '未下发过' }}</b>
        </span>
      </template>
      <span v-else class="hint">本服务启动后尚未下发过模式类指令，机器人当前模式未知。</span>
      <span class="hint">（趴下/起立/步态/电量见「监控」页，来自 0x0901 实时上报）</span>
    </div>

    <!-- 1. 心跳保活 -->
    <div class="block">
      <div class="block-title">
        心跳保活<small>0x21040001 · 文档要求 ≥ 2Hz</small>
      </div>
      <div class="row">
        <button v-if="!hbRunning" class="btn" :disabled="!enabled || estop" @click="onStartHeartbeat">
          开启心跳
        </button>
        <button v-else class="btn" @click="onStopHeartbeat">停止心跳</button>
        <span class="hb-pill" :class="hbRunning ? 'on' : 'off'">
          <span class="hb-dot" :class="{ beating: hbRunning }" />
          {{ hbRunning ? '心跳运行中' : '心跳已停止' }}
        </span>
        <span v-if="hbRunning" class="hb-meta mono">
          租约剩余 {{ status?.lease_remaining }}s · {{ hbSinceText }} · 已续约 {{ hbBeatCount }} 次
        </span>
        <span v-else-if="hbRestarting" class="hint">正在自动恢复心跳…</span>
      </div>
      <div class="hint">
        当前周期 {{ status?.heartbeat_interval ?? 0.25 }}s（约 {{ (1 / (status?.heartbeat_interval || 0.25)).toFixed(1) }}Hz），
        租约 {{ status?.heartbeat_lease ?? 5 }}s。心跳期间会同时重发当前速度指令。
        切换页面标签<b>不会</b>影响心跳；只有主动停止、停用通道、急停或关闭页面才会终止。
      </div>
    </div>

    <!-- 2. 常用指令（数量较少，合并同一行，卡片式边框区分） -->
    <div class="block quick-card">
      <div class="block-title">常用指令<small>模式 / 其他</small></div>
      <div v-for="g in quickGroups" :key="g.group" class="quick-row">
        <span class="quick-label">{{ g.group }}</span>
        <div class="chips">
          <button
            v-for="cmd in g.items"
            :key="cmd.name"
            class="chip-btn"
            :class="{ danger: cmd.danger }"
            :disabled="!enabled || estop"
            :title="`${cmd.code_hex}（type=${cmd.type}）${cmd.note ? ' · ' + cmd.note : ''}`"
            @click="onPreset(cmd)"
          >
            {{ cmd.name }}
            <span v-if="cmd.danger" class="mark">!</span>
          </button>
        </div>
      </div>
      <div class="hint">
        ⚠️ 速度指令（0x0140 / 0x0145 / 0x0141）<b>必须先切到自主模式</b>，否则机器人不会响应。
      </div>
    </div>

    <!-- 3. 状态指令 -->
    <div v-if="groupMap['状态']" class="block">
      <div class="block-title">状态指令<small>{{ groupMap['状态'].length }} 条</small></div>
      <div class="chips">
        <button
          v-for="cmd in groupMap['状态']"
          :key="cmd.name"
          class="chip-btn"
          :class="{ danger: cmd.danger }"
          :disabled="!enabled || estop"
          :title="`${cmd.code_hex}（type=${cmd.type}）${cmd.note ? ' · ' + cmd.note : ''}`"
          @click="onPreset(cmd)"
        >
          {{ cmd.name }}
          <span v-if="cmd.danger" class="mark">!</span>
        </button>
      </div>
    </div>

    <!-- 4. 步态指令 -->
    <div v-if="groupMap['步态']" class="block">
      <div class="block-title">步态指令<small>{{ groupMap['步态'].length }} 条</small></div>
      <div class="chips">
        <button
          v-for="cmd in groupMap['步态']"
          :key="cmd.name"
          class="chip-btn"
          :class="{ danger: cmd.danger }"
          :disabled="!enabled || estop"
          :title="`${cmd.code_hex}（type=${cmd.type}）${cmd.note ? ' · ' + cmd.note : ''}`"
          @click="onPreset(cmd)"
        >
          {{ cmd.name }}
          <span v-if="cmd.danger" class="mark">!</span>
        </button>
      </div>
    </div>

    <!-- 5. 动作指令与 AI -->
    <div v-if="groupMap['动作'] || groupMap['AI']" class="block">
      <div class="block-title">
        动作指令与 AI<small>表演动作 / AI 步态</small>
      </div>
      <div v-if="groupMap['动作']" class="sub-block">
        <span class="quick-label">动作</span>
        <div class="chips">
          <button
            v-for="cmd in groupMap['动作']"
            :key="cmd.name"
            class="chip-btn"
            :class="{ danger: cmd.danger }"
            :disabled="!enabled || estop"
            :title="`${cmd.code_hex}（type=${cmd.type}）${cmd.note ? ' · ' + cmd.note : ''}`"
            @click="onPreset(cmd)"
          >
            {{ cmd.name }}
            <span v-if="cmd.danger" class="mark">!</span>
          </button>
        </div>
      </div>
      <div v-if="groupMap['AI']" class="sub-block">
        <span class="quick-label">AI</span>
        <div class="chips">
          <button
            v-for="cmd in groupMap['AI']"
            :key="cmd.name"
            class="chip-btn"
            :class="{ danger: cmd.danger }"
            :disabled="!enabled || estop"
            :title="`${cmd.code_hex}（type=${cmd.type}）${cmd.note ? ' · ' + cmd.note : ''}`"
            @click="onPreset(cmd)"
          >
            {{ cmd.name }}
            <span v-if="cmd.danger" class="mark">!</span>
          </button>
        </div>
      </div>
      <div class="hint">
        带 <span class="mark small">!</span> 的为高风险动作，点击后需二次确认；且各自有前置状态要求（见按钮悬停提示）。
      </div>
    </div>

    <!-- 兜底：后端新增但未在此列出的分组 -->
    <div v-for="g in restGroups" :key="g.group" class="block">
      <div class="block-title">{{ g.group }}指令<small>{{ g.items.length }} 条</small></div>
      <div class="chips">
        <button
          v-for="cmd in g.items"
          :key="cmd.name"
          class="chip-btn"
          :class="{ danger: cmd.danger }"
          :disabled="!enabled || estop"
          :title="`${cmd.code_hex}（type=${cmd.type}）${cmd.note ? ' · ' + cmd.note : ''}`"
          @click="onPreset(cmd)"
        >
          {{ cmd.name }}
          <span v-if="cmd.danger" class="mark">!</span>
        </button>
      </div>
    </div>

    <!-- 自定义报文 -->
    <div class="block">
      <div class="block-title">自定义报文<small>code / 指令值 / type / data（头字段按十六进制）</small></div>
      <div class="form">
        <label>
          code
          <input v-model="custom.code" class="hex-in mono" spellcheck="false" placeholder="0x21040001" />
        </label>
        <label>
          指令值
          <input v-model="custom.value" class="hex-in mono" spellcheck="false" placeholder="0x00000000" />
        </label>
        <label>
          type
          <input v-model="custom.type" class="hex-in mono" spellcheck="false" placeholder="0x00000000" />
        </label>
        <label>
          data
          <input v-model.number="custom.data" type="number" step="0.01" />
        </label>
        <button class="btn primary" :disabled="!enabled || estop" @click="onSendCustom">发送指令</button>
      </div>
      <div class="hint">
        头字段填十六进制（自动忽略 0x 前缀与空格）；type=0 发简单指令（12B，忽略 data），
        type=1 发复杂指令（20B，data 按 double 打包，仅此处需要十进制物理量）。
      </div>
      <div class="form raw">
        <input v-model="rawHex" class="hex-input mono" placeholder="原始十六进制，如 4001000008000000..." />
        <button class="btn ghost" :disabled="!enabled || estop" @click="onSendRaw">发送原始报文</button>
      </div>
    </div>

    <!-- 6. 速度指令（最底部） -->
    <div class="block">
      <div class="block-title">
        速度指令<small>复杂指令 · 0x0140 / 0x0145 / 0x0141 · 需自主模式</small>
      </div>

      <div class="sliders">
        <label v-for="axis in VEL_AXES" :key="axis">
          <span>
            {{ LIMITS[axis].label }}
            <em>{{ LIMITS[axis].hint }}</em>
          </span>
          <div class="vel-line">
            <input
              v-model.number="vel[axis]"
              type="range"
              :min="LIMITS[axis].min"
              :max="LIMITS[axis].max"
              :step="LIMITS[axis].step"
              :disabled="!enabled || estop"
            />
            <input
              class="vel-num mono"
              type="number"
              :min="LIMITS[axis].min"
              :max="LIMITS[axis].max"
              :step="LIMITS[axis].step"
              :disabled="!enabled || estop"
              :value="velText[axis]"
              @input="onVelInput(axis, $event)"
              @change="onVelCommit(axis, $event)"
              @blur="onVelCommit(axis, $event)"
              @keyup.enter="onVelCommit(axis, $event)"
            />
            <span class="vel-unit">{{ LIMITS[axis].unit }}</span>
          </div>
        </label>
      </div>

      <div class="row">
        <button class="btn primary" :disabled="!enabled || estop" @click="onSendVelocity">发送速度</button>
        <button class="btn warn" :disabled="!enabled || estop" @click="onZeroVelocity">速度归零</button>
      </div>

      <!-- 模拟操作摇杆 -->
      <div class="joy-wrap">
        <div class="joy-head">
          <span>模拟操作摇杆</span>
          <div class="joy-opts">
            <label class="joy-radio">
              <input type="radio" value="xy" :checked="joyMode === 'xy'" @change="onJoyModeChange('xy')" />
              前后 + 左右
            </label>
            <label class="joy-radio">
              <input type="radio" value="xyaw" :checked="joyMode === 'xyaw'" @change="onJoyModeChange('xyaw')" />
              前后 + 转向
            </label>
            <label class="joy-radio">
              <input v-model="joyLive" type="checkbox" />
              拖动时实时下发
            </label>
          </div>
        </div>
        <div
          ref="joyEl"
          class="joy"
          :class="{ disabled: !enabled || estop }"
          @pointerdown="onJoyDown"
          @pointermove="onJoyMove"
          @pointerup="onJoyUp"
          @pointercancel="onJoyUp"
        >
          <span class="joy-axis joy-axis-v">前</span>
          <span class="joy-axis joy-axis-h">{{ joyMode === 'xy' ? '右' : '右转' }}</span>
          <div class="joy-knob" :class="{ active: joyActive }" :style="knobStyle" />
        </div>
        <div class="joy-read mono">
          前后 {{ velText.x }} · 左右 {{ velText.y }} · 旋转 {{ velText.yaw }}
        </div>
      </div>

      <div class="hint">
        取值范围来自文档 1.2.12：前后 ±1.0、左右 ±0.5、旋转 ±1.5（后端会二次限幅）。
        文本框超出范围会自动收敛到边界，非法输入在失焦/回车后回退到上一次有效值。
        摇杆与滑块、文本框<b>双向同步</b>；松手自动回中（所控两轴归零）。
      </div>
    </div>

    <!-- 危险指令二次确认 -->
    <div v-if="pendingDanger" class="confirm">
      <div class="confirm-text">
        确认下发高风险指令 <b>{{ pendingDanger.name }}</b>（{{ pendingDanger.code_hex }}）？
        <span v-if="pendingDanger.note">{{ pendingDanger.note }}</span>
      </div>
      <div class="row">
        <button class="btn danger" @click="doPreset(pendingDanger)">确认下发</button>
        <button class="btn ghost" @click="cancelDanger">取消</button>
      </div>
    </div>

    <!-- 反馈 -->
    <div v-if="notice" class="notice" :class="notice.ok ? 'ok' : 'bad'">{{ notice.text }}</div>
    <div v-if="lastResult?.packet" class="result">
      <div class="result-head">
        <span>{{ lastPacketText }}</span>
        <span class="mono hex">{{ lastResult.packet.hex }}</span>
      </div>
      <div class="result-stat">
        累计发送 {{ status?.sent_packets ?? 0 }} 包 · 失败 {{ status?.failed_packets ?? 0 }} 包
      </div>
    </div>
  </section>
</template>

<style scoped>
.alert {
  padding: 10px 12px;
  margin-bottom: 14px;
  font-size: 12.5px;
  line-height: 1.6;
  border-radius: 8px;
}

.alert.muted { color: #475569; background: #f1f5f9; border: 1px solid #e2e8f0; }
.alert.danger { color: #7f1d1d; background: #fef2f2; border: 1px solid #fecaca; }
.alert .live { color: #b91c1c; }

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

/* 默认按钮为中性描边。
   蓝色实心只保留给「当前选中项」或「该区主操作」——否则所有按钮都像处于激活态，
   看不出 ros / sniff / auto 哪个在生效。 */
.btn {
  padding: 6px 14px;
  font-size: 13px;
  color: #334155;
  background: #ffffff;
  border: 1px solid #dbe2ea;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn:hover:not(:disabled) { background: #f1f5f9; border-color: #cbd5e1; }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }

.btn.primary { color: #fff; background: #2563eb; border-color: #2563eb; }
.btn.primary:hover:not(:disabled) { background: #1d4ed8; border-color: #1d4ed8; }

.btn.danger { color: #fff; background: #dc2626; border-color: #dc2626; font-weight: 600; }
.btn.danger:hover:not(:disabled) { background: #b91c1c; border-color: #b91c1c; }

.btn.warn { color: #fff; background: #f59e0b; border-color: #f59e0b; }
.btn.warn:hover:not(:disabled) { background: #d97706; border-color: #d97706; }

.btn.ghost { color: #475569; background: var(--chip-bg); border: 1px solid #dfe5ec; }

/* 发包统计：心跳 / 业务分开累计 */
.sent-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.sent-stats .stat {
  padding: 4px 10px;
  font-size: 11.5px;
  color: #334155;
  background: #f8fafc;
  border: 1px solid #e6ecf3;
  border-radius: 8px;
}

.sent-stats .stat b { font-size: 13px; }
.sent-stats .stat.hb { color: #166534; background: #f0fdf4; border-color: #bbf7d0; }
.sent-stats .stat.biz { color: #1e40af; background: #eff6ff; border-color: #bfdbfe; }
.sent-stats .stat.fail { color: #991b1b; background: #fef2f2; border-color: #fecaca; }

/* 当前模式回显条 */
.mode-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 8px 0 14px;
  padding: 8px 10px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  background: #f8fafc;
  font-size: 12px;
}
.mode-strip .mode-label { font-weight: 600; color: #334155; margin-right: 2px; }
.mode-strip .mode-chip {
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1e40af;
}
.mode-strip .mode-chip.empty {
  border-color: #e2e8f0;
  background: #f1f5f9;
  color: #64748b;
}
.mode-strip .hint { color: #94a3b8; }

/* 数据源自检 */
.diag {
  padding: 10px 12px;
  margin-top: 10px;
  background: #f8fafc;
  border: 1px solid #e6ecf3;
  border-radius: 8px;
}

.diag.ok { background: #f0fdf4; border-color: #bbf7d0; }
.diag.warn { background: #fffbeb; border-color: #fde68a; }
.diag.fail { background: #fef2f2; border-color: #fecaca; }

.diag-head {
  margin-bottom: 6px;
  font-size: 12px;
  color: #334155;
}

.diag-head .dim { margin-left: 8px; color: #94a3b8; }

.diag-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.diag-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  padding: 2px 0;
  font-size: 11.5px;
  color: #334155;
}

.tick { flex: none; width: 12px; font-weight: 700; }
.tick.ok { color: #16a34a; }
.tick.no { color: #dc2626; }

.diag-list .dim { color: #94a3b8; }

.diag-hint {
  margin-top: 6px;
  padding-top: 6px;
  font-size: 11.5px;
  line-height: 1.6;
  color: #475569;
  border-top: 1px dashed #e6ecf3;
}

.block {
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px dashed #e6ecf3;
}

.block-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.block-title small {
  margin-left: 8px;
  font-size: 11px;
  font-weight: 400;
  color: #94a3b8;
}

/* 常用指令：卡片式边框与其它分区隔开 */
.quick-card {
  padding: 12px;
  margin-top: 14px;
  background: #fcfdff;
  border: 1px solid #dbe4ef;
  border-radius: 10px;
}

.quick-card .block-title { margin-bottom: 8px; }

.quick-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 6px 0;
}

.quick-row + .quick-row { border-top: 1px solid #eef2f7; }

.quick-label {
  flex: none;
  width: 40px;
  font-size: 11.5px;
  color: #94a3b8;
}

.sub-block {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 6px 0;
}

.sub-block + .sub-block { border-top: 1px solid #eef2f7; }

.chips { display: flex; flex-wrap: wrap; gap: 8px; }

.chip-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  font-size: 13px;
  color: #1e293b;
  background: #f8fafc;
  border: 1px solid #dbe2ea;
  border-radius: 6px;
  cursor: pointer;
}

.chip-btn:hover:not(:disabled) {
  color: #fff;
  background: #2563eb;
  border-color: #2563eb;
}

.chip-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.chip-btn.danger {
  color: #991b1b;
  background: #fef2f2;
  border-color: #fecaca;
}

.chip-btn.danger:hover:not(:disabled) {
  color: #fff;
  background: #dc2626;
  border-color: #dc2626;
}

.mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: #dc2626;
  border-radius: 50%;
}

.mark.small { width: 12px; height: 12px; font-size: 9px; vertical-align: middle; }

.hint { margin-top: 8px; font-size: 11.5px; color: #94a3b8; line-height: 1.6; }

/* ---- 心跳 ---- */
.hb-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  font-size: 12px;
  border-radius: 999px;
}

.hb-pill.on { color: #166534; background: #dcfce7; }
.hb-pill.off { color: #64748b; background: #f1f5f9; }

.hb-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #94a3b8;
}

.hb-dot.beating {
  background: #16a34a;
  animation: hb-pulse 1s ease-in-out infinite;
}

@keyframes hb-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.5); opacity: 0.5; }
}

@media (prefers-reduced-motion: reduce) {
  .hb-dot.beating { animation: none; }
}

.hb-meta { font-size: 11.5px; color: #64748b; }

/* ---- 速度 ---- */
.sliders {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.sliders label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  font-size: 12px;
  color: var(--text-sub);
  background: #f8fafc;
  border: 1px solid #e6ecf3;
  border-radius: 8px;
}

.sliders em { font-style: normal; color: #94a3b8; }

.vel-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vel-line input[type='range'] { flex: 1; min-width: 0; }

.vel-num {
  width: 74px;
  padding: 4px 6px;
  font-size: 12.5px;
  text-align: right;
  border: 1px solid #dbe2ea;
  border-radius: 6px;
}

.vel-unit { flex: none; font-size: 11px; color: #94a3b8; }

/* ---- 摇杆 ---- */
.joy-wrap {
  padding: 12px;
  margin-top: 12px;
  background: #fcfdff;
  border: 1px solid #dbe4ef;
  border-radius: 10px;
}

.joy-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 12.5px;
  font-weight: 600;
  color: #334155;
}

.joy-opts { display: flex; flex-wrap: wrap; gap: 10px; }

.joy-radio {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  font-weight: 400;
  color: var(--text-sub);
}

.joy {
  position: relative;
  width: 140px;
  height: 140px;
  margin: 0 auto;
  background: #f1f5f9;
  border: 1px solid #dbe2ea;
  border-radius: 50%;
  touch-action: none;
  cursor: crosshair;
  user-select: none;
}

.joy.disabled { opacity: 0.45; pointer-events: none; }

.joy-axis {
  position: absolute;
  font-size: 10.5px;
  color: #94a3b8;
}

.joy-axis-v { top: 6px; left: 50%; transform: translateX(-50%); }
.joy-axis-h { top: 50%; right: 6px; transform: translateY(-50%); }

.joy-knob {
  position: absolute;
  width: 40px;
  height: 40px;
  background: #2563eb;
  border: 2px solid #fff;
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.2);
  transform: translate(-50%, -50%);
}

.joy-knob.active { background: #1d4ed8; }

.joy-read {
  margin-top: 10px;
  font-size: 11.5px;
  color: #64748b;
  text-align: center;
}

.status-pill { padding: 3px 10px; font-size: 12px; border-radius: 999px; }
.status-pill.on { color: #166534; background: #dcfce7; }
.status-pill.off { color: #64748b; background: #f1f5f9; }

.form { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; }

.form label {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  color: var(--text-sub);
}

.form input {
  width: 130px;
  padding: 5px 8px;
  font-size: 13px;
  border: 1px solid #dbe2ea;
  border-radius: 6px;
}

.form.raw { margin-top: 10px; }
.hex-input { flex: 1; min-width: 240px; width: auto !important; font-size: 12px !important; }

/* 自定义报文的头字段：等宽 + 稍窄，容纳 0x21040001 这类 10 字符 */
.hex-in { width: 116px !important; font-size: 12px !important; letter-spacing: 0.2px; }

.confirm {
  padding: 12px;
  margin-top: 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
}

.confirm-text {
  margin-bottom: 10px;
  font-size: 12.5px;
  color: #7f1d1d;
  line-height: 1.6;
}

.notice { padding: 7px 12px; margin-top: 12px; font-size: 12.5px; border-radius: 6px; }
.notice.ok { color: #166534; background: #dcfce7; }
.notice.bad { color: #991b1b; background: #fee2e2; }

.result {
  padding: 10px 12px;
  margin-top: 10px;
  background: #f8fafc;
  border: 1px solid #e6ecf3;
  border-radius: 8px;
}

.result-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: space-between;
  font-size: 12.5px;
  color: #334155;
}

.result-head .hex {
  max-width: 100%;
  overflow: hidden;
  color: #64748b;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-stat { margin-top: 6px; font-size: 11.5px; color: #94a3b8; }
</style>
