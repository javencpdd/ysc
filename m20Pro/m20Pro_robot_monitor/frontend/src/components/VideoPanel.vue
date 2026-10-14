<template>
  <div class="panel">
    <h3>相机画面 <small>（HLS · 延迟 1–3s · 不转码）</small></h3>

    <!-- 降级：源不可用/未开启时给明确提示，绝不白屏（PLAN §6.3 / T3.4） -->
    <div v-if="!status.available" style="color: var(--warn); padding: 8px 0">
      ⚠ {{ status.enabled ? '视频源不可用' : '视频功能未开启' }}
      <span v-if="status.last_error" style="color: var(--muted); font-size: 12px">
        （{{ status.last_error }}）
      </span>
      <div v-if="!status.enabled" style="color: var(--muted); font-size: 12px; margin-top: 4px">
        提示：机器人休眠时相机不通电，需先「唤醒」再开启视频
      </div>
    </div>

    <div v-show="status.available" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px">
      <button :class="{ danger: current === FRONT }" @click="switchTo(FRONT)">前相机</button>
      <button :class="{ danger: current === BACK }" @click="switchTo(BACK)">后相机</button>
      <span style="color: var(--muted); font-size: 12px; align-self: center">
        {{ status.rtsp_url }} · 切片 {{ status.last_segment_age }}s 前
      </span>
    </div>

    <video
      v-show="status.available"
      ref="videoEl"
      controls
      muted
      autoplay
      playsinline
      style="width: 100%; max-width: 900px; background: #000; border-radius: 6px; min-height: 240px"
    ></video>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import Hls from 'hls.js'
import { getJson, postJson } from '../api/index.js'

const FRONT = 'rtsp://127.0.0.1:8554/video1'
const BACK = 'rtsp://127.0.0.1:8554/video2'

const videoEl = ref(null)
const status = ref({ enabled: false, available: false })
const current = ref(FRONT)
let hls = null
let timer = null

async function refresh () {
  try {
    status.value = await getJson('/api/v1/video/status')
  } catch (err) {
    status.value = { enabled: false, available: false, last_error: '无法读取视频状态' }
  }
}

function attach () {
  if (hls || !videoEl.value || !status.value.available) return
  const src = '/hls/live.m3u8'
  if (Hls.isSupported()) {
    hls = new Hls({ lowLatencyMode: true, liveSyncDurationCount: 2 })
    hls.loadSource(src)
    hls.attachMedia(videoEl.value)
    hls.on(Hls.Events.ERROR, (_e, data) => {
      if (data.fatal) {
        hls.destroy()
        hls = null
        refresh()
      }
    })
  } else if (videoEl.value.canPlayType('application/vnd.apple.mpegurl')) {
    videoEl.value.src = src   // Safari 原生 HLS
  }
}

function detach () {
  if (hls) {
    hls.destroy()
    hls = null
  }
}

async function switchTo (url) {
  current.value = url
  await postJson('/api/v1/video/source', { url })
  detach()
  await refresh()
  attach()
}

onMounted(async () => {
  await refresh()
  attach()
  // 每 3s 探一次：上游恢复后自动重挂（降级 → 恢复）
  timer = setInterval(async () => {
    const wasAvailable = status.value.available
    await refresh()
    if (!wasAvailable && status.value.available) attach()
  }, 3000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  detach()
})
</script>
