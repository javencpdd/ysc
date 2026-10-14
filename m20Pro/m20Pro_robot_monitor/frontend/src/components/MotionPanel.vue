<template>
  <div class="panel">
    <h3>
      运动控制
      <small>（分层开放 · 当前 {{ ctrl.enabled ? 'L1 低危可控' : 'L0 只监' }}）</small>
    </h3>

    <!-- 整机指令：开关 / 急停 / 站立(起立) / 趴下 / 唤醒。
         未开启控制时置灰 —— 需先点最左侧「开启控制（需确认）」。 -->
    <div class="btn-row">
      <button v-if="!ctrl.enabled" @click="onEnable">开启控制（需确认）</button>
      <button v-else @click="onDisable">停用控制</button>
      <!-- 软急停：安全手段优先于开关，L0 下也可用 -->
      <button class="danger" @click="estop">软急停</button>
      <button v-if="ctrl.estop" @click="clearEstop">解除急停</button>
      <button :disabled="!ctrl.enabled" :title="disabledTip" @click="send('stand_up')">站立</button>
      <button :disabled="!ctrl.enabled" :title="disabledTip" @click="send('lie_down')">趴下</button>
      <button :disabled="!ctrl.enabled" :title="disabledTip" @click="send('wake_up')">唤醒</button>
    </div>

    <div class="grid" style="margin-bottom: 10px">
      <div class="kv"><span>租约剩余</span><span>{{ (ctrl.lease_remaining ?? 0).toFixed(1) }} s</span></div>
      <div class="kv"><span>急停锁定</span><span>{{ ctrl.estop ? '是' : '否' }}</span></div>
      <div class="kv"><span>已发指令</span><span>{{ ctrl.sent_packets ?? 0 }}</span></div>
      <div class="kv"><span>被拒指令</span><span>{{ ctrl.rejected_packets ?? 0 }}</span></div>
    </div>

    <div style="margin-bottom: 10px">
      <label>步态：</label>
      <select v-model="gait" :disabled="!ctrl.enabled" @change="setGait">
        <option :value="0x1001">基础（标准）</option>
        <option :value="0x1003">楼梯（标准）</option>
        <option :value="0x3002">平地（敏捷）</option>
        <option :value="0x3003">楼梯（敏捷）</option>
      </select>
    </div>

    <!-- 速度控制：虚拟摇杆（模拟遥感，交互参考 lite3 控制面板） -->
    <div class="joy-wrap">
      <div class="joy-head">
        <span class="block-title">速度控制（虚拟摇杆）</span>
        <div class="joy-opts">
          <label class="joy-radio">
            <input type="radio" value="xy" :checked="joyMode === 'xy'" @change="setJoyMode('xy')" />
            前后 + 左右平移
          </label>
          <label class="joy-radio">
            <input type="radio" value="xyaw" :checked="joyMode === 'xyaw'" @change="setJoyMode('xyaw')" />
            前后 + 转向
          </label>
        </div>
      </div>

      <div
        ref="joyEl"
        class="joy"
        :class="{ disabled: !ctrl.enabled || ctrl.estop }"
        @pointerdown="onJoyDown"
        @pointermove="onJoyMove"
        @pointerup="onJoyUp"
        @pointercancel="onJoyUp"
      >
        <span class="joy-axis joy-axis-top">前</span>
        <span class="joy-axis joy-axis-bottom">后</span>
        <span class="joy-axis joy-axis-left">{{ joyMode === 'xy' ? '左移' : '左转' }}</span>
        <span class="joy-axis joy-axis-right">{{ joyMode === 'xy' ? '右移' : '右转' }}</span>
        <div class="joy-knob" :class="{ active: joyActive }" :style="knobStyle" />
      </div>

      <div class="joy-read">
        下发轴值 前后 <b>{{ readout.x }}</b> ·
        {{ joyMode === 'xy' ? '左右' : '旋转' }} <b>{{ readout.h }}</b>
        <span class="dim">（拖动中约 16Hz 持续下发 · 松手 → 零位停止，不软急停）</span>
      </div>

      <div class="joy-tip">
        ⚠ 平移/转向存在车侧起动阈值：推杆幅度太小可能原地不动（前后方向阈值较低）；
        <b>左右平移 / 转向未经实车标定</b>，请小幅慢试。
        松手 / 断流只会「零位停」，绝不自动软急停；急停请点上方「软急停」。
      </div>

      <div class="speed-line">
        <label for="speed-limit">速度上限</label>
        <input
          id="speed-limit"
          type="number"
          min="0.05"
          max="0.4"
          step="0.01"
          v-model.number="speed"
          @change="normalizeSpeed"
        />
        <span class="speed-hint">0.05 ~ 0.40（默认 0.25 ≈ 实测舒适档；摇杆满舵 = 所填数值）</span>
      </div>
    </div>

    <div v-if="lastResult" class="last-result">最近结果：{{ lastResult }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  control: { type: Object, default: () => ({}) },
  sendCommand: { type: Function, required: true },
  sendAxis: { type: Function, required: true },
  stopAxis: { type: Function, required: true },
  estop: { type: Function, required: true },
  clearEstop: { type: Function, required: true },
  enableControl: { type: Function, required: true },
  disableControl: { type: Function, required: true },
  renewLease: { type: Function, default: null }
})

const ctrl = ref(props.control)
watch(() => props.control, (v) => { ctrl.value = v || {} }, { deep: true })

const gait = ref(0x1001)
const lastResult = ref('')
const disabledTip = computed(() => (ctrl.value.enabled ? '' : '需先点「开启控制（需确认）」'))

// ---------------------------------------------------------------- 速度上限
// 摇杆满舵轴值 = 所填数值（2026-10-15 真机实测：
//   0.25 ≈ 0.32 m/s 舒适档 / 0.40 ≈ 0.54 m/s 上限 / ≥0.70 危险）
const SPEED_MIN = 0.05
const SPEED_MAX = 0.4
const SPEED_DEFAULT = 0.25

function loadSpeed () {
  try {
    const v = Number(window.localStorage.getItem('m20.speedLimit'))
    if (isFinite(v) && v >= SPEED_MIN && v <= SPEED_MAX) return v
  } catch (e) { /* localStorage 不可用时回落默认 */ }
  return SPEED_DEFAULT
}

const speed = ref(loadSpeed())

function normalizeSpeed () {
  let v = Number(speed.value)
  if (!isFinite(v) || v <= 0) v = SPEED_DEFAULT
  v = Math.min(SPEED_MAX, Math.max(SPEED_MIN, Math.round(v * 100) / 100))
  speed.value = v
  try { window.localStorage.setItem('m20.speedLimit', String(v)) } catch (e) { /* ignore */ }
  return v
}

// ---------------------------------------------------------------- 虚拟摇杆
// 交互参考 lite3 ControlPanel.vue 的"模拟操作摇杆"：指针事件 + 单位圆归一化。
// 与 lite3 的关键差异：m20 后端 20Hz 看门狗要求 ≤250ms 持续 feed，
// 所以拖动期间由定时器（60ms）持续下发 —— 即使指针不动也必须续发；
// 松手时先等所有在途请求落地，再调 stopAxis（避免残余 feed 复位看门狗）。
const JOY_SEND_MS = 60        // 持续 feed 间隔（后端超时 250ms，留 4 倍余量抗 WiFi 丢包）
const JOY_MAX_INFLIGHT = 3    // 允许同时在途的请求数（网络慢时多发增强抗抖动）
const JOY_DEAD_ZONE = 0.08    // 中心死区：8% 行程内归零（防误触）
const JOY_R = 48              // 手柄行程半径（px），与 CSS 中 .joy(140px) / .joy-knob(44px) 配套

const joyEl = ref(null)
const joyActive = ref(false)
const joyMode = ref('xy')                  // 'xy' = 前后+左右平移；'xyaw' = 前后+转向
const joyVec = ref({ x: 0, h: 0 })         // 归一化 [-1,1]：x 上推为正(前进)；h 左为正
const readout = ref({ x: '0.00', h: '0.00' })
let joyTimer = null
let joyInFlight = 0

const joyHAxis = computed(() => (joyMode.value === 'xy' ? 'y' : 'yaw'))

/** 归一化摇杆值 → 六轴指令值（满舵 = speed；x 正=前进 / y 正=左移 / yaw 正=左转） */
function joyValues () {
  const s = speed.value
  const v = { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 }
  v.x = Math.round(joyVec.value.x * s * 100) / 100
  v[joyHAxis.value] = Math.round(joyVec.value.h * s * 100) / 100
  return v
}

/** 手柄位置由 joyVec 反推 —— 与读数、模式切换双向同步 */
const knobStyle = computed(() => ({
  left: `calc(50% + ${(-joyVec.value.h * JOY_R).toFixed(1)}px)`,
  top: `calc(50% + ${(-joyVec.value.x * JOY_R).toFixed(1)}px)`
}))

function updateReadout () {
  const s = speed.value
  readout.value = {
    x: (joyVec.value.x * s).toFixed(2),
    h: (joyVec.value.h * s).toFixed(2)
  }
}

function setJoyFromPoint (clientX, clientY) {
  const el = joyEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  const r = Math.min(rect.width, rect.height) / 2
  let dx = (clientX - cx) / r
  let dy = (clientY - cy) / r
  const len = Math.hypot(dx, dy)
  if (len > 1) { dx /= len; dy /= len }   // 限制在单位圆内（满舵 = 圆边）
  if (len < JOY_DEAD_ZONE) {              // 中心死区：轻微误触归零
    joyVec.value = { x: 0, h: 0 }
  } else {
    // 屏幕 y 向下为正：上推 = 前进 → x = -dy；右推 = 右移/右转 → h = -dx
    joyVec.value = { x: -dy, h: -dx }
  }
  updateReadout()
}

/** 持续 feed：每 60ms 一发（看门狗 250ms 超时，留 4 倍余量）。
 *  不阻塞发送（最多 3 发在途）—— 网络慢时让多发请求同时在飞，
 *  提高"250ms 内至少一发到达"的概率（2026-10-15 事故教训：宁可多发）。 */
function pushJoy () {
  if (joyInFlight >= JOY_MAX_INFLIGHT) return
  joyInFlight++
  props.sendAxis(joyValues(), true)
    .catch((err) => {
      lastResult.value = '轴指令发送失败：' + (err && err.message ? err.message : err)
    })
    .finally(() => { joyInFlight-- })
}

function startJoyLoop () {
  if (joyTimer) return
  pushJoy()   // 立即首发，不等第一个 60ms tick
  joyTimer = setInterval(pushJoy, JOY_SEND_MS)
}

function stopJoyLoop () {
  if (joyTimer) {
    clearInterval(joyTimer)
    joyTimer = null
  }
}

function sleep (ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function onJoyDown (ev) {
  if (!ctrl.value.enabled || ctrl.value.estop) return
  // 先续约防抖：页面可能刚从后台回来（定时器被浏览器节流、租约已过期），
  // 不先续约的话首推会被租约闸拒发（表现为"推杆没反应"）
  if (props.renewLease) props.renewLease().catch(() => {})
  joyActive.value = true
  ev.currentTarget.setPointerCapture && ev.currentTarget.setPointerCapture(ev.pointerId)
  setJoyFromPoint(ev.clientX, ev.clientY)
  startJoyLoop()
}

function onJoyMove (ev) {
  if (!joyActive.value) return
  setJoyFromPoint(ev.clientX, ev.clientY)
}

/** 松开摇杆的统一收尾：停循环 → 清值 → 等在途落地 → 零位停止。
 *  松手 / 页面切后台都走这里（2026-10-15 二次事故后加固）。 */
async function releaseJoy (msg) {
  if (!joyActive.value) return
  joyActive.value = false
  stopJoyLoop()
  joyVec.value = { x: 0, h: 0 }
  updateReadout()
  // 等所有在途请求落地（最多 800ms）再发 stopAxis —— 否则残余 feed 可能在
  // 暂停之后到达服务端、把看门狗重新激活（松开后车继续走）
  const t0 = Date.now()
  while (joyInFlight > 0 && Date.now() - t0 < 800) await sleep(25)
  try {
    await props.stopAxis()
    lastResult.value = msg || '已松开：零位停止（不触发软急停）'
  } catch (err) {
    lastResult.value = '停止指令下发失败（车侧 150ms 看门狗将自动清零）：'
      + (err && err.message ? err.message : err)
  }
}

function onJoyUp () {
  releaseJoy()
}

// 页面切后台 / 最小化：自动按"松手"处理。
// 防的是：按住摇杆切走 → 浏览器节流定时器 → feed 断流
//（2026-10-15 二次事故的边界情况之一；后端"断流自动软急停"已同步切除）
function onVisibilityChange () {
  if (document.hidden && joyActive.value) {
    releaseJoy('页面切至后台：已自动零位停止')
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

/** 切换摇杆水平轴：清掉上一模式遗留值，避免残速 */
function setJoyMode (mode) {
  if (joyMode.value === mode) return
  joyMode.value = mode
  joyVec.value = { x: joyVec.value.x, h: 0 }
  updateReadout()
}

watch(speed, updateReadout)

// ---------------------------------------------------------------- 指令
async function send (name, params = {}) {
  const res = await props.sendCommand(name, params)
  lastResult.value = res.ok ? `${name} 已下发` : `被拒：${res.reason} ${res.detail || ''}`
}

async function setGait () {
  await send('gait', { param: gait.value })
}

async function onEnable () {
  if (!window.confirm('确认开启机器人控制？开启后可通过本页驱动机器人运动。')) return
  const res = await props.enableControl()
  lastResult.value = res.ok ? '控制已开启（L1）' : '开启失败'
}

async function onDisable () {
  await props.disableControl()
  lastResult.value = '控制已停用（回到 L0 只监）'
}
</script>

<style scoped>
.btn-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

/* ---- 虚拟摇杆 ---- */
.joy-wrap {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.joy-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.joy-opts {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.joy-radio {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
}

.joy {
  position: relative;
  width: 140px;
  height: 140px;
  margin: 0 auto;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 50%;
  touch-action: none;
  cursor: crosshair;
  user-select: none;
  -webkit-user-select: none;
}

/* 十字参考线 */
.joy::before,
.joy::after {
  content: '';
  position: absolute;
  background: var(--line);
}

.joy::before { left: 50%; top: 12px; bottom: 12px; width: 1px; transform: translateX(-50%); }
.joy::after { top: 50%; left: 12px; right: 12px; height: 1px; transform: translateY(-50%); }

.joy.disabled { opacity: 0.45; pointer-events: none; }

.joy-axis {
  position: absolute;
  font-size: 10px;
  color: var(--muted);
  pointer-events: none;
}

.joy-axis-top { top: 5px; left: 50%; transform: translateX(-50%); }
.joy-axis-bottom { bottom: 5px; left: 50%; transform: translateX(-50%); }
.joy-axis-left { left: 5px; top: 50%; transform: translateY(-50%); }
.joy-axis-right { right: 5px; top: 50%; transform: translateY(-50%); }

.joy-knob {
  position: absolute;
  z-index: 1;
  width: 44px;
  height: 44px;
  background: var(--accent);
  border: 2px solid rgba(255, 255, 255, 0.85);
  border-radius: 50%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.joy-knob.active { background: #0ea5e9; }

.joy-read {
  margin-top: 12px;
  font-size: 12px;
  color: var(--muted);
  text-align: center;
}

.joy-read b {
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.joy-read .dim { margin-left: 6px; font-size: 11px; opacity: 0.8; }

.joy-tip {
  margin-top: 8px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--warn);
  text-align: center;
}

.joy-tip b { color: var(--warn); }

.speed-line {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}

.speed-line label { font-size: 13px; }

.speed-line input {
  width: 72px;
  padding: 4px 8px;
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 6px;
  font-size: 13px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.speed-hint { font-size: 11.5px; color: var(--muted); }

.last-result {
  margin-top: 10px;
  font-size: 12px;
  color: var(--muted);
  word-break: break-all;
}
</style>
