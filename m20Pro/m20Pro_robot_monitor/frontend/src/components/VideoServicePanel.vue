<template>
  <!-- 推流服务（2026-10-17）：两条链分开控，别混。
       local = 厂商本地推流（mediamtx + push_video.sh）→ 控制台画面靠它
       relay = 自研外推中继（m20video.service）→ 转到远端 RTMP，关掉画面照旧 -->
  <div class="vsvc">
    <div class="vsvc-head">
      <span class="vsvc-title">推流服务</span>
      <span v-if="!state.targets.local" class="vsvc-err">状态不可用</span>
      <span class="vsvc-spacer"></span>
      <button class="mini" type="button" :disabled="busy" @click="load">刷新</button>
    </div>

    <div v-if="err" class="vsvc-err">{{ err }}</div>

    <div v-for="key in ['local', 'relay']" :key="key" class="vsvc-row">
      <div class="vsvc-meta">
        <span class="dot" :class="lvl(key)"></span>
        <span class="vsvc-label">{{ t(key).label || key }}</span>
        <span class="vsvc-summary" :class="lvl(key)">{{ t(key).summary || '—' }}</span>
        <span class="vsvc-detail">{{ detailOf(key) }}</span>
      </div>
      <div class="vsvc-acts">
        <button
          v-for="a in ACTIONS"
          :key="a.key"
          class="mini"
          type="button"
          :disabled="busy"
          :title="a.tip(t(key).label)"
          @click="act(key, a.key)"
        >{{ a.label }}</button>
      </div>
    </div>

    <div class="vsvc-note">
      「本地推流」才是喂控制台画面的那条；「外推中继」只是把画面转发给远端服务器，
      关掉它控制台照旧能看。画面黑但本地推流显示"在出流"时，问题在相机或取流侧。
    </div>
    <div v-if="!state.ok && state.detail" class="vsvc-note err">{{ state.detail }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getJson, postJson } from '../api/index.js'

// ⚠️ 初始 ok:true 是刻意的：状态**取不到**不该把动作按钮一起锁死。
//    之前动作按钮多带了一个 `!state.ok` 条件，一旦 /video/service 拉取失败
//    （helper 慢/超时），就只剩「刷新」可点、启停全灰 —— 用户的原话正是
//    "只能刷新不能停止"（2026-10-17 真踩）。动作本身与状态读取是**独立**的：
//    该让它去试，失败了再报错，而不是先替它断定不可用。
const state = ref({ ok: true, targets: {} })
const busy = ref(false)
const err = ref('')
let timer = null

const ACTIONS = [
  { key: 'start', label: '启动', tip: (l) => `启动${l}` },
  { key: 'stop', label: '停止', tip: (l) => `停止${l}（会让画面消失，需确认）` },
  { key: 'restart', label: '重启', tip: (l) => `重启${l}（画面黑/卡住时先试这个）` }
]

const t = (key) => (state.value.targets || {})[key] || {}
const lvl = (key) => t(key).level || 'off'

function detailOf (key) {
  const d = t(key)
  if (key === 'local') {
    return `进程 ${d.processes ?? '—'} · 编码器 ${d.gst ?? '—'} · ` +
      `HLS ${d.hls_video1 ?? '—'}/${d.hls_video2 ?? '—'}`
  }
  return `unit ${d.unit ?? '—'} · 进程 ${d.processes ?? '—'} · ` +
    `目标 ${d.target_tcp ? '可达' : '不可达'}`
}

async function load () {
  try {
    state.value = await getJson('/api/v1/video/service')
  } catch (e) {
    state.value = { ok: false, targets: {}, detail: String(e && e.message ? e.message : e) }
  }
}

async function act (target, action) {
  const label = t(target).label || target
  const isStop = action === 'stop'
  if (isStop) {
    const ok = window.confirm(
      `确认停止「${label}」？\n\n` +
      (target === 'local'
        ? '这是喂控制台画面的那条 —— 停掉后本页画面会立刻消失，需要重新「启动」才回来。'
        : '这只是对外的转发，控制台画面不受影响。')
    )
    if (!ok) return
  }
  busy.value = true
  err.value = ''
  try {
    const res = await postJson('/api/v1/video/service',
      { target, action, confirmed: isStop })
    if (res && res.ok) {
      state.value = { ok: true, targets: res.targets || {} }
    } else {
      err.value = `操作被拒：${(res && res.reason) || '未知'} ${(res && res.detail) || ''}`
    }
  } catch (e) {
    err.value = '请求失败：' + (e && e.message ? e.message : e)
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  load()
  // 15s 一次：推流状态变化不快，没必要跟画面重连那样频繁打后端
  timer = setInterval(load, 15000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.vsvc {
  margin-bottom: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: var(--panel-2, #f7f8fa);
  border: 1px solid var(--border, #d8dce3);
  border-radius: 6px;
}
.vsvc-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.vsvc-title { font-weight: 600; }
.vsvc-spacer { flex: 1 1 auto; }
.vsvc-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
  border-top: 1px solid var(--line);
}
.vsvc-meta { flex: 1 1 auto; min-width: 0; }
.vsvc-label { margin-right: 6px; }
.vsvc-summary { font-weight: 600; }
.vsvc-summary.ok { color: var(--ok, #2e9e5b); }
.vsvc-summary.warn { color: var(--warn, #c47f17); }
.vsvc-summary.off { color: var(--muted, #888); }
.vsvc-detail {
  margin-left: 8px;
  color: var(--muted, #888);
  font-variant-numeric: tabular-nums;
}
.vsvc-acts { flex: 0 0 auto; display: flex; gap: 4px; }
.vsvc-note { margin-top: 4px; line-height: 1.6; color: var(--muted, #888); }
.vsvc-note.err, .vsvc-err { color: var(--danger, #d0453b); }
.dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 5px;
  border-radius: 50%;
  background: currentColor;
  vertical-align: middle;
}
.dot.ok { color: var(--ok, #2e9e5b); }
.dot.warn { color: var(--warn, #c47f17); }
.dot.off { color: var(--muted, #aaa); }
.mini {
  padding: 1px 8px;
  font-size: 11px;
  font-family: inherit;
  color: var(--muted, #888);
  background: transparent;
  border: 1px solid var(--line);
  border-radius: 4px;
}
.mini:hover:not(:disabled) { color: var(--text, #222); border-color: var(--accent, #2f6fed); }
.mini:disabled { opacity: 0.5; }
</style>
