<template>
  <div class="panel">
    <h3>
      相机画面
      <small>（前后双路 · {{ webrtcOn ? 'WebRTC 低延迟' : 'HLS 兜底' }}）</small>
    </h3>

    <!-- 整体未开启 / 配置不可用：给明确提示，绝不白屏（PLAN §6.3 / T3.4） -->
    <div v-if="!cfg.enabled" style="color: var(--warn); padding: 8px 0">
      ⚠ 视频功能未开启（后端 `M20_VIDEO__ENABLED=false`）
    </div>

    <template v-if="cfg.enabled">
      <div class="vbar">
        <button :class="{ active: layout === 'both' }" @click="layout = 'both'">并排双路</button>
        <button :class="{ active: layout === 'front' }" @click="layout = 'front'">仅前</button>
        <button :class="{ active: layout === 'back' }" @click="layout = 'back'">仅后</button>
        <button @click="reloadAll">重连</button>
        <span class="hint">
          源：MediaMTX {{ locationHost }} ·
          WHEP :{{ cfg.webrtc.port }} / HLS :{{ cfg.hls.port }}
        </span>
      </div>

      <div class="vgrid" :class="{ single: layout !== 'both' }">
        <div
          v-for="s in streams"
          :key="s.key"
          v-show="isShown(s.key)"
          class="vcell"
        >
          <div class="vhead">
            <b>{{ s.label }}</b>
            <span class="badge" :class="badgeClass(s.key)">{{ badgeText(s.key) }}</span>
          </div>

          <video
            :ref="(el) => setVideoEl(s.key, el)"
            controls
            muted
            autoplay
            playsinline
            class="v"
          ></video>

          <div v-if="runtime[s.key]?.state === 'failed'" class="verr">
            ⚠ {{ runtime[s.key].detail || '取流失败' }}
            <div class="hint">机器人休眠时相机不通电 —— 需先「唤醒」</div>
          </div>
          <div v-else class="hint">{{ runtime[s.key]?.detail || '' }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import Hls from 'hls.js'
import { getJson } from '../api/index.js'
import { createWhepPlayer, isWebRtcSupported } from '../webrtc/whep.js'

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
  for (const s of streams.value) stopStream(s.key)
  startAll()
}

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
  if (st === 'connected') return 'ok'
  if (st === 'failed') return 'bad'
  return 'warn'
}

onMounted(async () => {
  await loadCfg()
  await startAll()
  // 每 5s 探一次：上游（MediaMTX/相机）恢复后自动重挂
  timer = setInterval(async () => {
    await loadCfg()
    for (const s of streams.value) {
      const st = runtime[s.key]?.state
      if (st === 'failed' || st === 'idle') startStream(s)
    }
  }, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  for (const key of Object.keys(runtime)) stopStream(key)
})
</script>

<style scoped>
.vbar {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.vbar button.active {
  background: var(--accent, #2f6fed);
  color: #fff;
}
.vgrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.vgrid.single {
  grid-template-columns: 1fr;
}
@media (max-width: 900px) {
  .vgrid {
    grid-template-columns: 1fr;
  }
}
.vcell {
  min-width: 0;
}
.vhead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-size: 13px;
}
.v {
  width: 100%;
  background: #000;
  border-radius: 6px;
  min-height: 200px;
  aspect-ratio: 4 / 3;
}
.badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid currentColor;
}
.badge.ok { color: var(--ok, #2e9e5b); }
.badge.warn { color: var(--warn, #c8901e); }
.badge.bad { color: var(--danger, #d0453b); }
.hint {
  color: var(--muted, #888);
  font-size: 12px;
  margin-top: 4px;
}
.verr {
  color: var(--danger, #d0453b);
  font-size: 13px;
  margin-top: 6px;
}
</style>
