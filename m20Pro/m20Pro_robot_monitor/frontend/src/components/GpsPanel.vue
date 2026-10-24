<template>
  <div class="panel">
    <h3>
      GPS 定位
      <small>（只读 · 显示 M20 上报的 GPS 数据包）</small>
      <span class="spacer" />
      <span v-if="hasGps" class="pill" :class="located ? 'pill-ok' : 'pill-warn'">
        <span class="status-dot" :class="located ? 'ok' : 'warn pulse'" />
        {{ located ? '已定位' : '未定位' }}
      </span>
      <span v-else class="pill pill-muted">无数据</span>
    </h3>

    <!-- GPS 供电开关（1101/3，2026-10-17 抓包破解）：
         GPS 模块随车供电，可以单独开/关。注意这与「GPS 时间同步」(1101/16)
         是两回事——那条只影响时钟，不动供电。 -->
    <div class="devbar">
      <span class="devbar-label">GPS 供电</span>
      <DeviceToggle
        label="GPS 模块"
        :value="gps.gps_enable ?? null"
        :disabled="!ctrl.enabled"
        :busy="!!devBusy"
        @set="setGpsPower"
      />
      <span v-if="!ctrl.enabled" class="hint">需先在「运动控制」页开启控制（L1）</span>
      <span v-if="devMsg" class="hint">{{ devMsg }}</span>
      <span v-if="devErr" class="hint err">{{ devErr }}</span>
    </div>

    <!-- 未拿到设备状态：给明确提示，绝不白屏 -->
    <div v-if="!hasGps" class="empty-state">
      <span class="empty-icon">∅</span>
      <span class="empty-title">暂未收到 GPS 数据</span>
      <span class="empty-desc">
        设备状态帧尚未就绪，或本机型未装配 GPS 模块。若机器人已开机且链路正常，请稍候数秒。
      </span>
    </div>

    <template v-if="hasGps">
      <!-- 定位状态一眼可见：不看懂 HDOP 也能判断"能不能信" -->
      <div v-if="!located" class="warn-box" style="margin-bottom: var(--sp-3)">
        ⚠ 当前<b>未定位</b>（经纬度为 0、卫星数 {{ satText }}）——
        室内 / 冷启动 / 天线遮挡都会导致无定位，数值仅供参考
      </div>

      <div class="block-title" style="margin-bottom: var(--sp-2)">定位结果</div>
      <div class="grid">
        <div class="kv"><span>纬度 Latitude</span><span>{{ n6(gps.gps_latitude) }}</span></div>
        <div class="kv"><span>经度 Longitude</span><span>{{ n6(gps.gps_longitude) }}</span></div>
        <div class="kv"><span>海拔 Altitude</span><span>{{ n2(gps.gps_altitude) }}</span></div>
        <div class="kv"><span>速度 Speed</span><span>{{ n2(gps.gps_speed) }}</span></div>
        <div class="kv"><span>航向 Course</span><span>{{ n2(gps.gps_course) }}</span></div>
        <div class="kv"><span>定位质量 FixQuality</span><span>{{ dash(gps.gps_fix_quality) }}</span></div>
        <div class="kv"><span>解算卫星数</span><span>{{ dash(gps.gps_num_satellites) }}</span></div>
        <div class="kv"><span>可见卫星数</span><span>{{ dash(gps.gps_visible_satellites) }}</span></div>
      </div>

      <div class="block-title" style="margin: var(--sp-4) 0 var(--sp-2)">
        精度因子（越小越好）
      </div>
      <div class="grid">
        <div class="kv"><span>HDOP 水平</span><span>{{ n2(gps.gps_hdop) }}</span></div>
        <div class="kv"><span>VDOP 垂直</span><span>{{ n2(gps.gps_vdop) }}</span></div>
        <div class="kv"><span>PDOP 位置</span><span>{{ n2(gps.gps_pdop) }}</span></div>
        <div class="kv"><span>GPS 供电开关</span><span>{{ onoff(gps.gps_enable) }}</span></div>
        <div class="kv"><span>卫星系统模式</span><span>{{ modeLabel }}</span></div>
      </div>

      <!-- 卫星系统模式（GPSMode = GNSS 系统掩码）
           位定义来自车侧 gps.yaml 的 sysMask 注释：bit0 GPS / bit4 BDS / bit8 GLONASS
           / bit12 Galileo / bit16 QZSS。这里**只显示星座真名**，不显示 69905 这种代号；
           原始掩码挪到下方原始数据包区。 -->
      <div class="devbar" style="margin-top: var(--sp-3)">
        <span class="devbar-label">卫星系统</span>
        <template v-for="opt in gpsModes" :key="opt.mask">
          <button
            class="mode-btn"
            :class="{ active: Number(gps.gps_mode) === opt.mask, 'btn-loading': devBusy === 'GPSMode' }"
            :disabled="!ctrl.enabled || !!devBusy"
            :title="modeTip(opt)"
            @click="setMode(opt.mask)"
          >{{ devBusy === 'GPSMode' ? '切换中…' : opt.label }}</button>
        </template>
        <span class="mask-hex">掩码 {{ gps.gps_mode_hex || '—' }}</span>
        <span v-if="!ctrl.enabled" class="hint">需先在「运动控制」页开启控制（L1）</span>
      </div>
      <div v-if="activeSystems.length" class="sys-chips">
        当前参与定位：<b v-for="sys in activeSystems" :key="sys" class="chip">{{ sys }}</b>
      </div>
      <div class="note mode-note">
        读数是<b>车侧实际生效值</b>（basic_server 收到 GNSS 节点上报后才更新，切换后约 1–2s 才收敛）。
        位定义取自车侧 <code>gps.yaml</code>：bit0 GPS · bit4 BDS · bit8 GLONASS · bit12 Galileo · bit16 QZSS。
      </div>

      <!-- 原始数据包：排查"上报了但解析错了"时看这里 -->
      <div class="raw-head">
        <span class="block-title">原始数据包（DeviceStatus.GPS 原样透传）</span>
        <button class="btn-sm btn-ghost" type="button" @click="showRaw = !showRaw">
          {{ showRaw ? '收起' : '展开' }}
        </button>
      </div>
      <pre v-if="showRaw" class="raw">{{ rawJson }}</pre>

      <div class="warn-box" style="margin-top: var(--sp-3)">
        ⚠ 字段<b>单位未见官方文档</b>（docs/04 未收录 GPS 字段说明），此处不做任何换算、
        原样显示上报值。GPS 同步开关是另一条指令（<code>1101/16</code> GPS 时间同步），与定位数据无关。
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJson } from '../api/index.js'
import DeviceToggle from './DeviceToggle.vue'
import { useDeviceSwitch } from '../composables/useDeviceSwitch.js'

const props = defineProps({
  // 设备状态（含 GPS 细粒度字段与 DevEnable）
  device: { type: Object, default: () => ({}) },
  // 控制通道状态（决定开关是否可用）
  control: { type: Object, default: () => ({}) },
  // 指令下发（由 App.vue 透传）
  sendCommand: { type: Function, default: null }
})

// ⚠️ 必须解构到顶层：Vue 3 模板只对**顶层** setup 绑定做 ref 解包，
// 写成 `dev.busy` 拿到的是 Ref 对象本身（恒真）→ `:disabled` 永远为真。
// 这正是 2026-10-17 用户反馈"供电开关按钮按不了"的根因。
// ⚠️ `flash` 同样必须解构：此前 setMode 里调用了 devFlash 但并未解构出来，
// 一旦触发会直接抛 ReferenceError（界面改造时一并补上）。
const { busy: devBusy, msg: devMsg, err: devErr,
        flash: devFlash, apply: devApply } = useDeviceSwitch(props)
const ctrl = computed(() => props.control || {})

const showRaw = ref(false)
const gps = computed(() => props.device || {})

// 可选卫星系统模式：从后端契约端点取（协议常量单一来源在 asdu_parser）
onMounted(async () => {
  try {
    const sc = await getJson('/api/v1/schema')
    gpsModes.value = sc.gps_modes || []
  } catch {
    /* 拿不到就不渲染切换器（只读字段仍在），不阻塞页面 */
  }
})

// 有任一 GPS 字段即可认为收到过 GPS 包（全 undefined 说明设备状态还没来）
const hasGps = computed(() =>
  ['gps_latitude', 'gps_longitude', 'gps_num_satellites', 'gps_fix_quality']
    .some((k) => gps.value[k] != null))

// 未定位判定：经纬度都是 0 —— 不猜 FixQuality 语义（无文档）
const located = computed(() => {
  const lat = Number(gps.value.gps_latitude || 0)
  const lon = Number(gps.value.gps_longitude || 0)
  return lat !== 0 || lon !== 0
})

const n2 = (v) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(2))
const n6 = (v) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(6))
const dash = (v) => (v == null ? '—' : String(v))
const onoff = (v) => (v == null ? '—' : (Number(v) ? '开' : '关'))
const satText = computed(() => dash(gps.value.gps_num_satellites))

// ---- 卫星系统模式（GPSMode 掩码，位定义见 asdu_parser.GPS_SYSTEM_BITS）----
// 可选清单从 /api/v1/schema 拉（协议常量单一来源在后端），前端**不硬编码掩码**
const gpsModes = ref([])
const modeLabel = computed(() => gps.value.gps_mode_label || dash(gps.value.gps_mode))
const activeSystems = computed(() => gps.value.gps_systems || [])

function modeTip (opt) {
  if (!ctrl.value.enabled) return '需先在「运动控制」页开启控制（L1）'
  const sys = (opt.systems || []).join(' + ') || '无'
  return `切换到「${opt.label}」：${sys}（GPSMode=${opt.hex}）\n`
    + '改的是 GNSS 接收机启用的星座组合，不涉及供电；切回「全系统」即恢复默认'
}

function labelOf (mask) {
  const hit = gpsModes.value.find((o) => Number(o.mask) === Number(mask))
  return hit ? hit.label : ('0x' + Number(mask).toString(16))
}

//: 车侧生效校验的等待时间。为什么要校验：
//: `DeviceStatus.DevEnable.GPSMode` 是 basic_server 收到 gps_node 上报后才更新的
//: **实际生效值**（下发瞬间会短暂显示期望值，1~2s 后被车侧真实值覆盖）。
//: 2026-10-17 实测：切到「仅 GPS」「仅北斗」确实生效（gps_node 日志里
//: `系统模式: GP/GB` 真的变了），但**切回「全系统」车侧不接受** ——
//: 指令被 basic_server 接受（ErrorCode 0）却不改 GNSS 模块。
//: 所以这里必须回读校验，如实告诉用户"没生效"，绝不假装成功。
const MODE_SETTLE_MS = 4000

async function setMode (mask) {
  const want = Number(mask)
  if (Number(gps.value.gps_mode) === want) return
  const res = await devApply('GPSMode', { GPSMode: want }, '', false)
  if (!(res && res.ok)) return
  setTimeout(() => {
    const now = Number(gps.value.gps_mode)
    if (now === want) {
      devFlash(`已切到「${labelOf(want)}」`)
    } else {
      devFlash(`⚠ 已下发但车侧未生效：当前仍为「${gps.value.gps_mode_label || now}」`
        + `（指令被车侧接受，但 GNSS 模块未应用 —— 属车侧驱动行为，非控制台故障）`, true)
    }
  }, MODE_SETTLE_MS)
}

// GPS 供电开关（1101/3 GPS）
function setGpsPower (v) {
  devApply('GPS', { GPS: v }, '', v === 0)
}

const rawJson = computed(() => {
  const raw = gps.value.gps
  if (!raw || typeof raw !== 'object') return '（无原始数据）'
  try {
    return JSON.stringify(raw, null, 2)
  } catch (e) {
    return String(raw)
  }
})
</script>

<style scoped>
.devbar-label {
  font-weight: 600;
  color: var(--text);
}

.hint.err { color: var(--danger); }

.mode-btn {
  min-height: 26px;
  padding: var(--sp-1) var(--sp-3);
  font-family: inherit;
  font-size: var(--fs-12);
  color: var(--muted);
  background: transparent;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
}
.mode-btn:hover:not(:disabled):not(.active) {
  color: var(--text);
  background: var(--panel-3);
  border-color: var(--line-strong);
}
.mode-btn.active {
  color: #fff;
  background: var(--accent-strong);
  border-color: var(--accent-strong);
  font-weight: 600;
}
.mode-btn:disabled { opacity: 0.45; }

.mask-hex {
  margin-left: var(--sp-1);
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  font-size: var(--fs-12);
}

.sys-chips {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--muted);
}
.mode-note { margin-top: var(--sp-2); }
.mode-note code {
  padding: 0 4px;
  font-family: var(--ff-mono);
  font-size: var(--fs-11);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-xs);
}

.sys-chips .chip {
  display: inline-block;
  margin-left: var(--sp-1);
  padding: 1px 8px;
  font-weight: 600;
  color: var(--text);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
}

.raw-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  margin: var(--sp-4) 0 var(--sp-2);
}

.raw {
  max-height: 320px;
  margin: 0;
  padding: var(--sp-2) var(--sp-3);
  overflow: auto;
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  line-height: 1.5;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}

/* .grid 的固定列数规则已收敛到全局 style.css，本面板不再重复定义 */
</style>
