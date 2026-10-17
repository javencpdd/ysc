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
      <button
        :disabled="!ctrl.enabled"
        :title="wakeTip"
        @click="send('wake_up')"
      >唤醒整车</button>
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

    <!-- 车侧实际反馈（2026-10-16 加）：推了摇杆车不动时看这里 -->
    <div class="grid" style="margin-bottom: 6px">
      <div class="kv"><span>运动状态</span><span>{{ motionLabel }}</span></div>
      <div class="kv"><span>当前步态</span><span>{{ gaitLabel }}</span></div>
      <div class="kv"><span>实际 前后 X</span><span>{{ n3(motion.linear_x) }} m/s</span></div>
      <div class="kv"><span>实际 左右 Y</span><span>{{ n3(motion.linear_y) }} m/s</span></div>
      <div class="kv"><span>实际 转向 ω</span><span>{{ n3(motion.omega_z) }} rad/s</span></div>
      <div class="kv"><span>关节回零</span><span>{{ zeroLabel }}</span></div>
      <div class="kv"><span>雷达供电 前/后</span><span>{{ lidarLabel }}</span></div>
    </div>

    <!-- 雷达供电开关（1101/3，2026-10-17 抓包破解）：
         可单独控制前/后雷达。**站立/RL 运动中关闭会被服务端拒绝**——
         雷达是运控的平衡参考输入，这是有意为之的保守策略（厂商 App 不拦，我们拦）。 -->
    <div class="devbar">
      <span>雷达供电：</span>
      <DeviceToggle
        label="前雷达"
        :value="props.device?.lidar_front ?? null"
        :disabled="!ctrl.enabled"
        :busy="!!devBusy"
        @set="(v) => setLidar('Front', v)"
      />
      <DeviceToggle
        label="后雷达"
        :value="props.device?.lidar_back ?? null"
        :disabled="!ctrl.enabled"
        :busy="!!devBusy"
        @set="(v) => setLidar('Back', v)"
      />
      <span v-if="devMsg" class="hint">{{ devMsg }}</span>
      <span v-if="devErr" class="hint err">{{ devErr }}</span>
    </div>

    <!-- 其他设备供电（同一条 1101/3，换 Items 键即可）：
         键名与语义全部经车侧日志逐条实证，见 patrol_codec.DEVICE_SWITCH_SPEC -->
    <div class="devbar">
      <span>其他设备：</span>
      <DeviceToggle
        v-for="d in OTHER_DEVICES"
        :key="d.key"
        :label="d.label"
        :value="props.device?.[d.field] ?? null"
        :disabled="!ctrl.enabled"
        :busy="!!devBusy"
        @set="(v) => setFlag(d.key, v)"
      />
      <!-- 风扇是 0~100 而非开关：同样用「开/关」两个选项，转速作为副标注 -->
      <DeviceToggle
        label="风扇"
        :value="props.device?.fan_speed ?? null"
        :hint="props.device?.fan_speed != null ? props.device.fan_speed : ''"
        :disabled="!ctrl.enabled"
        :busy="!!devBusy"
        @set="setFan"
      />
    </div>
    <div v-if="!motionReady" style="color: var(--warn); font-size: 12px; margin-bottom: 10px">
      ⚠ 当前「{{ motionLabel }}」—— 轴指令<b>只在「站立 / RL 控制」下生效</b>，请先点「站立」
    </div>
    <!-- 开机阻尼态：车侧默认 autoResetJointsZero=true，点「站立」时运控会先回零再起立 -->
    <div v-if="isBootDamping" class="gait-warn" style="margin-bottom: 10px">
      ⚠ 当前是「开机阻尼」态 —— 车侧默认开启<b>自动回零</b>
      （<code>autoResetJointsZero = true</code>），点「站立」后运控会<b>先完成关节回零再起立</b>，
      所以首次站立比后续站立慢、且中途不要干预。
    </div>
    <template v-else>
      <div v-if="joyLateralWarn" class="gait-warn">⚠ {{ joyLateralWarn }}</div>
      <div style="color: var(--muted); font-size: 12px; margin-bottom: 10px">
        诊断：发了横移却不动时，看「实际 左右 Y」—— 恒为 0 = 车侧没执行（步态不支持）；
        有值但机身不挪 = 轮足侧向打滑
      </div>
    </template>

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

    <!-- 定时移动（2026-10-16 加）：选方向 + 速度 + 秒数，后端计时到点自动停。
         计时放后端：浏览器定时器会被节流（切后台/省电），前端计时停不住车。 -->
    <div class="timed-wrap">
      <div class="joy-head">
        <span class="block-title">定时移动（方向 · 速度 · 秒数）</span>
        <span class="timed-state" :class="{ on: timedActive }">
          <template v-if="timedActive">
            执行中 · 剩余 {{ timedRemaining.toFixed(1) }} s / 共 {{ timedTotal.toFixed(1) }} s
          </template>
          <template v-else>空闲</template>
        </span>
      </div>
      <div class="timed-row">
        <label>方向
          <select v-model="timedDir" :disabled="timedActive">
            <option v-for="(d, key) in TIMED_DIRS" :key="key" :value="key">{{ d.label }}</option>
          </select>
        </label>
        <label>速度
          <input type="number" min="0.05" max="0.4" step="0.01" v-model.number="timedSpeed"
                 :disabled="timedActive" @change="clampTimedSpeed" />
        </label>
        <label>秒数
          <input type="number" min="0.5" max="30" step="0.5" v-model.number="timedSeconds"
                 :disabled="timedActive" @change="clampTimedSeconds" />
        </label>
        <label>通道
          <select v-model="timedChannel" :disabled="timedActive">
            <option value="steer">steer（2/21 主通道）</option>
            <option value="real">real（2/25 实时通道）</option>
          </select>
        </label>
        <button v-if="!timedActive" :disabled="!ctrl.enabled || ctrl.estop" :title="disabledTip"
                @click="startTimed">开始</button>
        <button v-else class="danger" @click="abortTimed">中止</button>
      </div>
      <div v-if="timedWarn" class="gait-warn">⚠ {{ timedWarn }}</div>
      <div class="timed-tip">
        到点自动「零位停止」（不软急停），计时在后端完成 —— 浏览器切后台也按时停。<br />
        横移（左移 / 右移）需先把步态切到「平地（敏捷）0x3002」：2026-10-16 实测，
        0x1001 基础（标准）下 Y 指令只原地调姿态、不位移（steer / real 两条通道一致）。
        「通道」选择保留作排查工具。
      </div>
    </div>

    <div v-if="lastResult" class="last-result">最近结果：{{ lastResult }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import DeviceToggle from './DeviceToggle.vue'
import { useDeviceSwitch } from '../composables/useDeviceSwitch.js'

const props = defineProps({
  control: { type: Object, default: () => ({}) },
  sendCommand: { type: Function, required: true },
  sendAxis: { type: Function, required: true },
  sendTimedAxis: { type: Function, required: true },
  stopAxis: { type: Function, required: true },
  estop: { type: Function, required: true },
  clearEstop: { type: Function, required: true },
  enableControl: { type: Function, required: true },
  disableControl: { type: Function, required: true },
  renewLease: { type: Function, default: null },
  refreshControl: { type: Function, default: null },
  //: 本面板是否可见（App.vue 标签页传入）。**切走即松手**：摇杆用了
  //  setPointerCapture，多指触屏下"一指按摇杆、一指切标签"会让捕获中的
  //  pointermove 继续喂看门狗——车会在看不见的标签后面继续走。
  active: { type: Boolean, default: true },
  //: 看门狗状态（定时移动倒计时来源；2026-10-16 加）
  watchdog: { type: Object, default: () => ({}) },
  // 车侧状态（诊断用）：实际速度反馈 + 当前步态 + 运动状态
  motion: { type: Object, default: () => ({}) },
  basic: { type: Object, default: () => ({}) },
  // 设备状态（2026-10-17 加）：提供 DevEnable 分设备供电使能
  device: { type: Object, default: () => ({}) }
})

const ctrl = ref(props.control)
watch(() => props.control, (v) => { ctrl.value = v || {} }, { deep: true })

// ---- 车侧实际速度反馈（2026-10-16 加）----
// 用途：推摇杆却不动时，用它判别"指令被忽略"还是"车在动但看不出来"：
//   · 发了 y=0.4 但 linear_y 恒为 0  → 车侧没执行横移（步态/模式不支持）
//   · linear_y 有非零值但机身位移极小 → 轮足侧向打滑，属能力所限
const n3 = (v) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(3))
const GAIT_LABEL = {
  4097: '0x1001 基础（标准）',
  4099: '0x1003 楼梯（标准）',
  12290: '0x3002 平地（敏捷）',
  12291: '0x3003 楼梯（敏捷）',
}
const gaitLabel = computed(() => {
  const g = props.basic?.gait
  if (!g) return '—'
  return GAIT_LABEL[g] || `0x${Number(g).toString(16)}`
})

// ---- 横移步态提示（2026-10-16 真机对照实验结论）----
// 实测：0x1001 基础（标准）步态下 Y 指令只原地调姿态、不位移，steer / real 两条通道
// 表现一致；切 0x3002 平地（敏捷）后横移生效（vy 抬升 2× 底噪 + 站高 0.574→0.46）。
// ⇒ 横移能力由**步态**决定，与通道无关。只提示、不拦截。
function lateralHint (g) {
  if (g === 0x1001) {
    return '「基础（标准）0x1001」不支持横移（2026-10-16 实测）—— Y 指令只会原地调整姿态、'
      + '不位移，请先切「平地（敏捷）0x3002」'
  }
  if (g === 0x1003) {
    return '「楼梯（标准）0x1003」与基础同系、横移未实测 —— 若原地不动请切「平地（敏捷）0x3002」'
  }
  return ''
}
const MOTION_LABEL = { 0: '空闲', 1: '站立', 2: '软急停阻尼', 3: '开机阻尼', 4: '趴下', 17: 'RL 控制' }
const motionLabel = computed(() => {
  const m = props.basic?.motion_state
  return m == null ? '—' : (MOTION_LABEL[m] || `未知(${m})`)
})
const motionReady = computed(() => [1, 17].includes(props.basic?.motion_state))

// ---- 关节回零（2026-10-17 取证）----
// 车侧 basic_server.toml 默认 `autoResetJointsZero = true`，BasicStatus 上报带
// `ResetJointsZero` 字段。值域未见官方文档，故标签由后端保守给出、前端不臆造。
const zeroLabel = computed(() => props.basic?.reset_joints_zero_label || '—')
// 开机阻尼态（MotionParam=3）：此时点「站立」，运控会先跑 ZeroCalibrationState 回零再起立
const isBootDamping = computed(() => props.basic?.motion_state === 3)

// ---- 设备供电开关（1101/3，2026-10-17 抓包破解）----
// 此前判断"协议未公开单独开/关雷达"是**错的** —— 抓包拿到 1101/3，
// Items 键名决定目标设备（Lidar/Video/GPS/...），已逐键经车侧日志实证。
// ⚠️ 必须解构到顶层：Vue 3 模板只对**顶层** setup 绑定做 ref 解包，
// 写成 `dev.busy` 拿到的是 Ref 对象本身（恒真）→ `:disabled` 永远为真。
// 这正是 2026-10-17 用户反馈"供电开关按钮按不了"的根因。
const { busy: devBusy, msg: devMsg, err: devErr,
        apply: devApply, setPair } = useDeviceSwitch(props)
const onoff = (v) => (v == null ? '—' : (Number(v) ? '开' : '关'))
const lidarLabel = computed(() => {
  const f = onoff(props.device?.lidar_front)
  const b = onoff(props.device?.lidar_back)
  return (f === '—' && b === '—') ? '—' : `${f} / ${b}`
})
const lidarVal = (side) => (side === 'Front' ? props.device?.lidar_front : props.device?.lidar_back)
const lidarOther = (side) => (side === 'Front' ? props.device?.lidar_back : props.device?.lidar_front)
function setLidar (side, v) {
  // 1101/3 是**整键覆写**，必须把另一路的当前值一起带上，
  // 否则只改一路会把没点的那路默认成 0（= 顺带关掉）。
  setPair('Lidar', side, v, lidarOther(side))
}

// 其他单路设备（键名/标签经车侧日志逐条实证，见 patrol_codec.DEVICE_SWITCH_SPEC）
const OTHER_DEVICES = [
  { key: 'LedHost', field: 'led_host', label: '主机电源指示灯' },
  { key: 'LedExt', field: 'led_ext', label: '外部负载指示灯' },
  { key: 'LoadPower', field: 'load_power', label: '外部负载供电' },
  { key: 'FP', field: 'fp', label: '对频模块' }
]
function setFlag (key, v) {
  devApply(key, { [key]: v }, '', v === 0)
}

// 风扇：0 与 100 两档（真机只实测过 100；转速语义未见文档，故不做连续滑杆）
async function setFan (v) {
  const next = v ? 100 : 0
  await devApply('FanSpeed', { FanSpeed: next }, '', next === 0)
}

// 唤醒 = 退出整车休眠（1101/6），会连带恢复相机/雷达/GPS/关节供电 —— 标注清楚避免误解
const wakeTip = computed(() => (ctrl.value.enabled
  ? '退出整车休眠（1101/6）—— 会同时恢复相机 / 雷达 / GPS / 关节供电'
  : disabledTip.value))

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
//: 摇杆「前后 + 左右平移」模式 + 标准系步态 → 提前警示横移不可用
const joyLateralWarn = computed(() => (joyMode.value === 'xy' ? lateralHint(props.basic?.gait) : ''))
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

// 切到别的标签 = 与"页面切后台"同级的松手条件（见 props.active 注释）：
// 摇杆有 setPointerCapture，隐藏后事件仍可能继续到达，必须显式收手。
watch(() => props.active, (on) => {
  if (!on && joyActive.value) releaseJoy('切换标签：已自动零位停止')
})

/** 切换摇杆水平轴：清掉上一模式遗留值，避免残速 */
function setJoyMode (mode) {
  if (joyMode.value === mode) return
  joyMode.value = mode
  joyVec.value = { x: joyVec.value.x, h: 0 }
  updateReadout()
}

watch(speed, updateReadout)

// ---------------------------------------------------------------- 定时移动（2026-10-16 加）
// 设计要点：计时放**后端**（前端 setInterval 会被浏览器节流，靠它停不住车）。
// 前端只负责：选参数 → 调一次 API → 轮询后端状态显示倒计时；中止 = 调 stopAxis。
// 通道 steer(2/21) / real(2/25)：两通道字段同构、订阅方不同，可做对照排查。
const TIMED_DIRS = {
  forward: { label: '前进', axes: { x: 1 } },
  back: { label: '后退', axes: { x: -1 } },
  left: { label: '左移', axes: { y: 1 } },
  right: { label: '右移', axes: { y: -1 } },
  yaw_left: { label: '左转', axes: { yaw: 1 } },
  yaw_right: { label: '右转', axes: { yaw: -1 } }
}
const TIMED_MIN_S = 0.5
const TIMED_MAX_S = 30

const timedDir = ref('forward')
const timedSpeed = ref(SPEED_DEFAULT)
const timedSeconds = ref(2)
const timedChannel = ref('steer')

const timedActive = computed(() => !!(props.watchdog && props.watchdog.timed_active))
const timedRemaining = computed(() => Number((props.watchdog && props.watchdog.timed_remaining) || 0))
const timedTotal = computed(() => Number((props.watchdog && props.watchdog.timed_total) || 0))

//: 选中方向是否含横移（左移 / 右移）
const timedIsLateral = computed(() => ['left', 'right'].includes(timedDir.value))
//: 本地实时提示（选横移方向 + 标准系步态）—— 比等服务端返回更早一步
const timedLateralWarn = computed(() => (timedIsLateral.value ? lateralHint(props.basic?.gait) : ''))
//: 后端响应携带的警示（``res.warning``）：本机 basic 数据滞后时的兜底
const timedServerWarn = ref('')
const timedWarn = computed(() => (timedIsLateral.value
  ? (timedLateralWarn.value || timedServerWarn.value)
  : ''))

function clampTimedSpeed () {
  let v = Number(timedSpeed.value)
  if (!isFinite(v) || v <= 0) v = SPEED_DEFAULT
  v = Math.min(SPEED_MAX, Math.max(SPEED_MIN, Math.round(v * 100) / 100))
  timedSpeed.value = v
  return v
}

function clampTimedSeconds () {
  let v = Number(timedSeconds.value)
  if (!isFinite(v) || v <= 0) v = 2
  v = Math.min(TIMED_MAX_S, Math.max(TIMED_MIN_S, Math.round(v * 2) / 2))
  timedSeconds.value = v
  return v
}

// 执行中每 500ms 轮询一次后端状态刷新倒计时（空闲不轮询，避免无谓请求）
let timedPoll = null
function stopTimedPoll () {
  if (timedPoll) { clearInterval(timedPoll); timedPoll = null }
}
function ensureTimedPoll () {
  if (timedPoll || !props.refreshControl) return
  timedPoll = setInterval(() => { props.refreshControl() }, 500)
}
watch(timedActive, (on) => { on ? ensureTimedPoll() : stopTimedPoll() }, { immediate: true })
onUnmounted(stopTimedPoll)

async function startTimed () {
  if (!ctrl.value.enabled) { lastResult.value = '需先开启控制（L1）'; return }
  if (timedActive.value) return
  const dir = TIMED_DIRS[timedDir.value] || TIMED_DIRS.forward
  const s = clampTimedSpeed()
  const secs = clampTimedSeconds()
  const vals = { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 }
  Object.keys(dir.axes).forEach((axis) => {
    vals[axis] = Math.round(dir.axes[axis] * s * 100) / 100
  })
  // 先续约：页面刚从后台回来时租约可能已过期，不续约首帧会被租约闸拒发
  if (props.renewLease) { try { await props.renewLease() } catch (e) { /* 忽略 */ } }
  try {
    const res = await props.sendTimedAxis(vals, secs, timedChannel.value)
    timedServerWarn.value = (res && res.warning) || ''
    if (res && res.ok) {
      lastResult.value = `定时移动已开始：${dir.label} ${s} × ${secs}s`
        + `（通道 ${timedChannel.value}，到点自动停止）`
    } else {
      lastResult.value = `被拒：${(res && res.reason) || '未知'} ${(res && res.detail) || ''}`
    }
  } catch (err) {
    timedServerWarn.value = ''
    lastResult.value = '定时移动请求失败：' + (err && err.message ? err.message : err)
  }
  if (props.refreshControl) props.refreshControl()
}

async function abortTimed () {
  try {
    await props.stopAxis()
    lastResult.value = '已中止定时移动：零位停止（不软急停）'
  } catch (err) {
    lastResult.value = '中止指令下发失败（车侧 150ms 看门狗将自动清零）：'
      + (err && err.message ? err.message : err)
  }
  if (props.refreshControl) props.refreshControl()
}

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
/* ---- 状态栅格：**固定列数**，不用 auto-fill ----
   2026-10-17 修复：全局 `.grid` 用 `repeat(auto-fill, minmax(150px, 1fr))`，
   容器宽度只要差几个像素，能容纳的列数就会从 4 跳到 3（反之亦然）→
   整块布局"突然换行"。改成固定列数后，列数只会在断点处变化，不再抖动。 */
/* 150px 是「标签 + 最长数值」的实测下限（如 "实际 转向 ω" + "-0.003 rad/s"），
   用 minmax() 给足冗余，值又是 nowrap，所以不会再出现"挤到下一行"。 */
.grid {
  grid-template-columns: repeat(4, minmax(150px, 1fr));
}
@media (max-width: 1180px) {
  .grid { grid-template-columns: repeat(3, minmax(150px, 1fr)); }
}
@media (max-width: 880px) {
  .grid { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
}
@media (max-width: 560px) {
  .grid { grid-template-columns: minmax(150px, 1fr); }
}

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

/* ---- 定时移动（2026-10-16 加） ---- */
.timed-wrap {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.timed-state {
  font-size: 12px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.timed-state.on { color: var(--ok); }

.timed-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.timed-row label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.timed-row select,
.timed-row input {
  padding: 4px 8px;
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 6px;
  font-size: 13px;
}

.timed-row input[type='number'] {
  width: 68px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.timed-tip {
  margin-top: 8px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--muted);
}

/* 横移步态警示（2026-10-16）：摇杆区 / 定时移动区共用 */
.devbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 8px;
  padding: 6px 8px;
  border: 1px solid var(--border, #d8dce3);
  border-radius: 6px;
  font-size: 12px;
  background: var(--panel-2, #f7f8fa);
}
.devbar .hint.err {
  color: var(--danger, #d0453b);
}
.gait-warn {
  margin: 6px 0 10px;
  padding: 6px 9px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--warn);
  border: 1px solid var(--warn);
  border-radius: 6px;
  background: color-mix(in srgb, var(--warn) 10%, transparent);
}

.last-result {
  margin-top: 10px;
  font-size: 12px;
  color: var(--muted);
  word-break: break-all;
}
</style>
