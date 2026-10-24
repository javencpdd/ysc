<template>
  <div class="panel">
    <h3>
      相机画面
      <small>（前后双路）</small>
      <span class="spacer" />
      <span class="pill" :class="webrtcOn ? 'pill-info' : 'pill-warn'"
            :title="webrtcOn ? '当前走 WebRTC（WHEP）低延迟通道，延迟通常低于 500ms' : 'WebRTC 不可用，已降级 HLS（延迟约 2–3s）'">
        {{ webrtcOn ? 'WebRTC 低延迟' : 'HLS 兜底' }}
      </span>
    </h3>

    <!-- 整体未开启 / 配置不可用：给明确提示，绝不白屏（PLAN §6.3 / T.4） -->
    <div v-if="!cfg.enabled" class="warn-box">
      ⚠ 视频功能未开启（后端 <code>M20_VIDEO__ENABLED=false</code>）——
      开启并重启服务后本页才会出现画面。
    </div>

    <template v-if="cfg.enabled">
      <!-- 相机供电 / 整车休眠 / 单相机开关（2026-10-17 取证）：
           相机随车供电 —— 进入休眠时 basic_server 会关掉 VIDEO_POWER，画面必然黑。
           退出整车休眠用 1101/6；**单独开/关某一路相机**用 1101/3 的
           {"Video":{"Front":..,"Back":..}}（抓包破解，车侧日志实证
           「设置广角相机开关 front:1 back:1」）。两者都就地暴露，省得切页。 -->
      <div class="devbar">
        <span class="devbar-label">相机供电</span>
        <DeviceToggle
          label="前相机"
          :value="videoFront ?? null"
          :disabled="!ctrl.enabled"
          :busy="!!devBusy"
          @set="(v) => setCam('Front', v)"
        />
        <DeviceToggle
          label="后相机"
          :value="videoBack ?? null"
          :disabled="!ctrl.enabled"
          :busy="!!devBusy"
          @set="(v) => setCam('Back', v)"
        />
        <span class="pill" :class="sleeping ? 'pill-warn' : 'pill-muted'"
              :title="sleeping ? '整车休眠中：相机不通电，画面全黑属正常现象' : '整车未休眠，相机应正常供电'">
          <span class="status-dot" :class="sleeping ? 'warn' : 'off'" />
          整车{{ sleepLabel }}
        </span>
        <!-- 常驻显示（不再只在休眠时出现）：相机随车供电，"相机没画面"时的第一反应
             就是确认整车是不是睡了；按钮也常驻，免得需要用的时候找不到。 -->
        <button
          class="btn-sm"
          :class="{ 'btn-loading': waking }"
          :disabled="!ctrl.enabled || waking"
          :title="wakeTip"
          @click="wakeUp"
        >{{ waking ? '唤醒中…' : '唤醒整车' }}</button>
        <span v-if="!ctrl.enabled" class="hint">需先在「运动控制」页开启控制（L1）</span>
        <span v-if="devMsg" class="hint">{{ devMsg }}</span>
        <span v-if="devErr" class="hint err">{{ devErr }}</span>
      </div>

      <!-- 推流服务开关（2026-10-17）：本地推流喂本页画面，外推中继只对外 -->
      <VideoServicePanel />

      <div class="vbar">
        <span class="vbar-group">
          <button
            class="btn-sm"
            :class="{ 'btn-primary': layout === 'both' }"
            :aria-pressed="layout === 'both'"
            title="同时显示前、后两路画面"
            @click="layout = 'both'"
          >双路并排</button>
          <button
            class="btn-sm"
            :class="{ 'btn-primary': layout === 'front' }"
            :aria-pressed="layout === 'front'"
            title="只显示前相机画面（两路仍在拉流，想省带宽请用「暂停拉流」）"
            @click="layout = 'front'"
          >只看前相机</button>
          <button
            class="btn-sm"
            :class="{ 'btn-primary': layout === 'back' }"
            :aria-pressed="layout === 'back'"
            title="只显示后相机画面（两路仍在拉流，想省带宽请用「暂停拉流」）"
            @click="layout = 'back'"
          >只看后相机</button>
        </span>

        <button
          class="btn-sm"
          :class="{ 'btn-loading': reconnecting }"
          :disabled="reconnecting"
          title="断开并重新建立取流连接（画面黑屏 / 卡住时先试这个）"
          @click="reloadAll"
        >{{ reconnecting ? '重连中…' : '重新连接' }}</button>

        <!-- 拉流开关（2026-10-18 加）：省 196 的上行带宽。
             实测单路 WHEP ≈ 50KB/s、HLS ≈ 25KB/s，两路常开约 100KB/s。
             除了这个手动开关，切走标签页/切走浏览器窗口也会自动停（见 flowReason）。 -->
        <button
          class="btn-sm"
          :class="flowWanted ? '' : 'btn-danger'"
          :disabled="!cfg.enabled"
          :title="flowTip"
          :aria-pressed="!flowWanted"
          @click="toggleFlow"
        >{{ flowWanted ? '暂停拉流' : '恢复拉流' }}</button>

        <span class="hint">
          源：MediaMTX {{ locationHost }} ·
          WHEP <span class="num">:{{ cfg.webrtc.port }}</span> /
          HLS <span class="num">:{{ cfg.hls.port }}</span>
        </span>
      </div>

      <!-- 没在拉流时说清楚为什么，别让人以为画面坏了 -->
      <div v-if="!flowWanted" class="warn-box" style="margin-bottom: var(--sp-3)">
        ⏸ {{ flowReason }}
        <span class="hint">（恢复后自动重连，推流服务本身不受影响）</span>
      </div>

      <!-- 一路流都没配：明确空状态，而不是留两格黑框 -->
      <div v-if="!streams.length" class="empty-state">
        <span class="empty-icon">∅</span>
        <span class="empty-title">未配置视频流</span>
        <span class="empty-desc">
          后端未返回任何流（<span class="mono">/api/v1/video/streams</span> 为空）。
          请确认 MediaMTX 与推流服务已启动。
        </span>
      </div>

      <div v-else class="vgrid" :class="{ single: layout !== 'both' }">
        <div
          v-for="s in streams"
          :key="s.key"
          v-show="isShown(s.key)"
          class="vcell"
        >
          <div class="vhead">
            <b>{{ s.label }}</b>
            <span class="pill" :class="badgeClass(s.key)">{{ badgeText(s.key) }}</span>
          </div>

          <div class="vframe">
            <video
              :ref="(el) => setVideoEl(s.key, el)"
              controls
              muted
              autoplay
              playsinline
              class="v"
            ></video>
            <!-- 连接中/重连中：覆盖式加载反馈，避免"黑屏 = 坏了"的误判 -->
            <div v-if="isBusyState(s.key)" class="vmask">
              <span class="spinner" />
              <span>{{ runtime[s.key]?.detail || '正在建立连接…' }}</span>
            </div>
          </div>

          <div v-if="runtime[s.key]?.state === 'failed'" class="verr">
            ⚠ {{ runtime[s.key].detail || '取流失败' }}
            <div class="hint">
              {{ sleeping
                ? '整车休眠中 —— 相机不通电，点上方「唤醒整车」'
                : '整车未休眠：多为推流管道或相机 USB 问题（可先点「重新连接」）' }}
            </div>
          </div>
          <div v-else class="hint">{{ runtime[s.key]?.detail || '' }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import Hls from 'hls.js'
import { getJson } from '../api/index.js'
import { createWhepPlayer, isWebRtcSupported } from '../webrtc/whep.js'
import DeviceToggle from './DeviceToggle.vue'
import VideoServicePanel from './VideoServicePanel.vue'
import { useDeviceSwitch } from '../composables/useDeviceSwitch.js'

// ---- 整车状态透传（2026-10-17 加）：相机随车供电，休眠就没画面 ----
const props = defineProps({
  device: { type: Object, default: () => ({}) },
  basic: { type: Object, default: () => ({}) },
  control: { type: Object, default: () => ({}) },
  sendCommand: { type: Function, default: null },
  // 相机标签页当前是否可见（App.vue 用 v-show 切页，组件不卸载，得自己知道）
  active: { type: Boolean, default: true }
})

// ---- 单相机供电开关（1101/3，2026-10-17 抓包破解）----
// ⚠️ 必须**解构到顶层**：Vue 3 模板只对顶层 setup 绑定做 ref 解包，
// 写成 `dev.busy` 拿到的是 Ref 对象本身（恒真）→ `:disabled` 永远为真 → 按钮全按不了。
// 这正是 2026-10-17 用户反馈"供电开关按钮我按不了"的根因。
const { busy: devBusy, msg: devMsg, err: devErr,
        flash: devFlash, setPair } = useDeviceSwitch(props)

const ctrl = ref(props.control)
watch(() => props.control, (v) => { ctrl.value = v || {} }, { deep: true })

const onoff = (v) => (v == null ? '—' : (Number(v) ? '开' : '关'))
const videoFront = computed(() => props.device?.video_front)
const videoBack = computed(() => props.device?.video_back)
const camValue = (side) => (side === 'Front' ? videoFront.value : videoBack.value)
const camOther = (side) => (side === 'Front' ? videoBack.value : videoFront.value)
// 1101/3 是**整键覆写**，必须把另一路当前值一起带上，否则会把没点的那路也关掉
function setCam (side, v) {
  setPair('Video', side, v, camOther(side))
}
// Sleep: 0=未休眠 1=已休眠 2=进入休眠中
const sleeping = computed(() => Number(props.basic?.sleep || 0) !== 0)
const sleepLabel = computed(() => props.basic?.sleep_label || '—')
const wakeTip = computed(() => {
  if (!ctrl.value.enabled) return '需先在「运动控制」页开启控制（L1）'
  return sleeping.value
    ? '退出整车休眠（1101/6）—— 会同时恢复相机 / 雷达 / GPS / 关节供电'
    : '整车未休眠时下发也安全（1101/6 幂等）；用于强制恢复相机 / 雷达供电'
})

// 唤醒 / 重连的加载态（仅展示用，不改变下发逻辑）
const waking = ref(false)
const reconnecting = ref(false)

async function wakeUp () {
  if (!props.sendCommand) return
  waking.value = true
  devFlash('唤醒下发中…')
  try {
    const res = await props.sendCommand('wake_up')
    devFlash(res && res.ok
      ? '唤醒已下发（1101/6）—— 供电恢复需数秒，稍后点「重新连接」'
      : `被拒：${(res && res.reason) || '未知'} ${(res && res.detail) || ''}`, !(res && res.ok))
  } catch (err) {
    devFlash('唤醒请求失败：' + (err && err.message ? err.message : err), true)
  } finally {
    waking.value = false
  }
}

const cfg = ref({ enabled: false, webrtc: {}, hls: {}, streams: [] })
const layout = ref('both')                 // both | front | back
const videoEls = reactive({})              // key -> <video>
const runtime = reactive({})               // key -> { mode, state, detail }

const whepPlayers = {}
const hlsPlayers = {}
let timer = null

const streams = computed(() => cfg.value.streams || [])
const webrtcOn = computed(() => cfg.value.webrtc?.enabled && isWebRtcSupported())
const locationHost = computed(() => (typeof window !== 'undefined' ? window.location.hostname : ''))

const isShown = (key) => layout.value === 'both' || layout.value === key
const isBusyState = (key) => ['connecting', 'reconnecting'].includes(runtime[key]?.state)

// ⚠️ 主机名必须取 location.hostname：写死 127.0.0.1 会让浏览器连自己（致命）
const scheme = () => (typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'https:' : 'http:')
const endpoint = (group, path) => {
  const g = cfg.value[group] || {}
  return `${scheme()}//${locationHost.value}:${g.port}${(g.endpoint || '').replace('{path}', path)}`
}

function setVideoEl (key, el) {
  if (el) videoEls[key] = el
}

async function loadCfg () {
  try {
    cfg.value = await getJson('/api/v1/video/streams')
  } catch {
    cfg.value = { enabled: false, webrtc: {}, hls: {}, streams: [] }
  }
}

function stopStream (key) {
  if (whepPlayers[key]) {
    whepPlayers[key].stop()
    delete whepPlayers[key]
  }
  if (hlsPlayers[key]) {
    hlsPlayers[key].destroy()
    delete hlsPlayers[key]
  }
  const el = videoEls[key]
  if (el) {
    el.srcObject = null
    el.removeAttribute('src')
    try { el.load() } catch { /* 忽略 */ }
  }
}

function fallbackToHls (s) {
  stopStream(s.key)
  const rt = runtime[s.key]
  rt.mode = 'hls'
  rt.state = 'connecting'
  rt.detail = 'HLS 兜底（延迟约 2–3s）'

  const el = videoEls[s.key]
  if (!el) return
  const url = endpoint('hls', s.path)
  if (Hls.isSupported()) {
    const hls = new Hls({ lowLatencyMode: true, liveSyncDurationCount: 2 })
    hls.loadSource(url)
    hls.attachMedia(el)
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      rt.state = 'connected'
      rt.detail = 'HLS 已连接（延迟约 2–3s）'
    })
    hls.on(Hls.Events.ERROR, (_e, data) => {
      if (data.fatal) {
        rt.state = 'failed'
        rt.detail = 'HLS 取流失败（检查相机是否通电 / MediaMTX 是否在跑）'
      }
    })
    hlsPlayers[s.key] = hls
  } else if (el.canPlayType('application/vnd.apple.mpegurl')) {
    el.src = url            // Safari 原生 HLS
    rt.state = 'connected'
    rt.detail = 'HLS 已连接（原生）'
  } else {
    rt.state = 'failed'
    rt.detail = '浏览器不支持 HLS'
  }
}

function startStream (s) {
  stopStream(s.key)
  const rt = runtime[s.key]
  rt.mode = 'webrtc'
  rt.state = 'connecting'
  rt.detail = ''

  if (!webrtcOn.value) {
    fallbackToHls(s)
    return
  }

  whepPlayers[s.key] = createWhepPlayer({
    url: endpoint('webrtc', s.path),
    maxRetries: 2,
    onTrack: (stream) => {
      const el = videoEls[s.key]
      if (!el) return
      el.srcObject = stream
      el.play().catch(() => {})
    },
    onState: (state, detail) => {
      rt.state = state
      if (detail) rt.detail = detail
      // WebRTC 重试耗尽 → 降级 HLS（保证"总有画面"）
      if (state === 'failed') fallbackToHls(s)
    },
    onLog: (msg) => {
      rt.detail = msg
    },
  })
  whepPlayers[s.key].start()
}

async function startAll () {
  for (const s of streams.value) {
    runtime[s.key] = runtime[s.key] || { mode: 'none', state: 'idle', detail: '' }
    startStream(s)
  }
}

function reloadAll () {
  reconnecting.value = true
  for (const s of streams.value) stopStream(s.key)
  startAll()
  // 连接是异步完成的；这里只给一个短时的视觉反馈，真实状态仍以 runtime 为准
  setTimeout(() => { reconnecting.value = false }, 800)
}

// ---------------------------------------------------------------- 拉流开关
// （2026-10-18 加，省 196 的上行带宽）
//
// 为什么需要：App.vue 用 v-show 切标签页（**不卸载组件**），而停流写在
// onUnmounted 里 → 控制台一开着，两路视频就一直在拉，不管你停在哪个标签页。
// 实测单路 WHEP ≈ 50KB/s、HLS ≈ 25KB/s，两路约 100KB/s 上行 —— 对走 WiFi
// 上联的 196 不是小数。
//
// 三个"想不想拉"的来源，取与：
//   · props.active   切到别的标签页 → 停（最常见的"我在干别的"）
//   · docHidden      切到别的浏览器标签/最小化 → 停（Page Visibility API）
//   · pulled         用户手动点「暂停拉流」→ 停（想停在相机页但不想占带宽）
const pulled = ref(true)
const docHidden = ref(false)
const flowing = ref(false)

const flowWanted = computed(() => props.active && pulled.value && !docHidden.value)

const flowReason = computed(() => {
  if (!props.active) return '已切到其他标签页 —— 拉流已暂停，回到「相机画面」自动恢复'
  if (docHidden.value) return '浏览器窗口已切走或最小化 —— 拉流已暂停，回到本窗口自动恢复'
  if (!pulled.value) return '已手动暂停拉流 —— 点「恢复拉流」继续'
  return ''
})

const flowTip = computed(() => flowWanted.value
  ? '暂停后不再从 196 拉视频（两路实测约 100KB/s 上行）；推流服务不受影响'
  : '恢复从 196 拉取前后两路视频')

function toggleFlow () {
  pulled.value = !pulled.value
}

function onVisibility () {
  docHidden.value = document.hidden
}

/** 探一次：上游恢复后自动重挂。仅在拉流中才跑。 */
async function probeOnce () {
  await loadCfg()
  for (const s of streams.value) {
    const st = runtime[s.key]?.state
    if (st === 'failed' || st === 'idle') startStream(s)
  }
}

function startFlow () {
  if (flowing.value) return
  flowing.value = true
  loadCfg().then(startAll)
  if (timer) clearInterval(timer)
  timer = setInterval(probeOnce, 5000)
}

function stopFlow () {
  flowing.value = false
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  // 逐路真拆：WHEP 走 DELETE 资源 + close PC，HLS 走 destroy
  for (const s of streams.value) stopStream(s.key)
}

watch(flowWanted, (want) => {
  if (want) startFlow()
  else stopFlow()
})

function badgeText (key) {
  const rt = runtime[key] || {}
  const map = {
    connected: '已连接',
    connecting: '连接中',
    reconnecting: '重连中',
    failed: '失败',
    idle: '待连接',
  }
  const mode = rt.mode === 'hls' ? 'HLS' : 'WebRTC'
  return rt.state === 'connected' ? `${mode} · 已连接` : `${mode} · ${map[rt.state] || rt.state || '待连接'}`
}

function badgeClass (key) {
  const st = runtime[key]?.state
  if (st === 'connected') return 'pill-ok'
  if (st === 'failed') return 'pill-bad'
  return 'pill-warn'
}

onMounted(async () => {
  // 浏览器窗口切走/最小化也停流（"我在干别的"最常见的形态）
  document.addEventListener('visibilitychange', onVisibility)
  docHidden.value = document.hidden
  // flowWanted 初值就是 true 时 watch 不会触发，这里显式起一次
  if (flowWanted.value) startFlow()
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibility)
  stopFlow()
})
</script>

<style scoped>
.devbar-label {
  font-weight: 600;
  color: var(--text);
}
.devbar .hint.err { color: var(--danger); }

.vbar {
  display: flex;
  gap: var(--sp-2);
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: var(--sp-3);
}

.vbar-group {
  display: inline-flex;
  gap: var(--sp-1);
  padding: 2px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}

.vgrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
}
.vgrid.single { grid-template-columns: 1fr; }

@media (max-width: 900px) {
  .vgrid { grid-template-columns: 1fr; }
}

.vcell { min-width: 0; }

.vhead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
  font-size: var(--fs-13);
}

.vframe { position: relative; }

.v {
  display: block;
  width: 100%;
  background: #000;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  min-height: 200px;
  aspect-ratio: 4 / 3;
}

/* 取流中：半透明遮罩 + 转圈，明确"在努力连"而不是"坏了" */
.vmask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--text);
  background: rgba(8, 13, 19, 0.68);
  border-radius: var(--r-md);
}

.hint {
  color: var(--muted);
  font-size: var(--fs-12);
  margin-top: var(--sp-1);
  line-height: 1.6;
}

.verr {
  margin-top: var(--sp-2);
  padding: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid var(--danger-line);
  border-radius: var(--r-sm);
}
.verr .hint { color: var(--muted); margin-top: var(--sp-1); }
</style>
