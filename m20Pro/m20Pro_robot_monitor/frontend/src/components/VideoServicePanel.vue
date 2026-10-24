<template>
  <!-- 推流服务（2026-10-17）：两条链分开控，别混。
       local = 厂商本地推流（mediamtx + push_video.sh）→ 控制台画面靠它
       relay = 自研外推中继（m20video.service）→ 转到远端 RTMP，关掉画面照旧 -->
  <div class="vsvc">
    <div class="vsvc-head">
      <span class="vsvc-title">推流服务</span>
      <span v-if="!state.targets.local" class="pill pill-warn">状态不可用</span>
      <span class="spacer" />
      <button
        class="btn-sm btn-ghost"
        type="button"
        :class="{ 'btn-loading': loading }"
        :disabled="busy || loading"
        title="重新读取两条推流链路的运行状态"
        @click="load"
      >{{ loading ? '读取中…' : '重新读取状态' }}</button>
    </div>

    <div v-if="err" class="danger-box" style="margin-bottom: var(--sp-2)">{{ err }}</div>

    <div v-for="key in ['local', 'relay']" :key="key" class="vsvc-row">
      <div class="vsvc-meta">
        <span class="dot" :class="lvl(key)" />
        <span class="vsvc-label">{{ t(key).label || key }}</span>
        <span class="pill" :class="summaryPill(key)">{{ t(key).summary || '—' }}</span>
        <span class="vsvc-detail">{{ detailOf(key) }}</span>
      </div>
      <div class="vsvc-acts">
        <button
          v-for="a in ACTIONS"
          :key="a.key"
          class="btn-sm"
          type="button"
          :class="{ 'btn-danger': a.key === 'stop', 'btn-loading': busyAct === a.key }"
          :disabled="busy"
          :title="a.tip(t(key).label)"
          @click="act(key, a.key)"
        >{{ busyAct === a.key ? actingLabel(a.key) : a.label }}</button>
      </div>
      <div v-if="busy" class="vsvc-busy"><span class="spinner" /> 操作执行中…</div>
    </div>

    <div class="note">
      「本地推流」才是喂控制台画面的那条；「外推中继」只是把画面转发给远端服务器，
      关掉它控制台照旧能看。画面黑但本地推流显示"在出流"时，问题在相机或取流侧。
    </div>
    <div v-if="!state.ok && state.detail" class="warn-box" style="margin-top: var(--sp-2)">
      {{ state.detail }}
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getJson, postJson } from '../api/index.js'
import { askConfirm } from '../composables/useConfirm.js'

// ⚠️ 初始 ok:true 是刻意的：状态**取不到**不该把动作按钮一起锁死。
//    之前动作按钮多带了一个 `!state.ok` 条件，一旦 /video/service 拉取失败
//    （helper 慢/超时），就只剩「刷新」可点、启停全灰 —— 用户的原话正是
//    "只能刷新不能停止"（2026-10-17 真踩）。动作本身与状态读取是**独立**的：
//    该让它去试，失败了再报错，而不是先替它断定不可用。
const state = ref({ ok: true, targets: {} })
const busy = ref(false)
const loading = ref(false)
const err = ref('')
/** 正在执行的动作（'start' | 'stop' | 'restart'）—— 用于按按钮显示加载态 */
const busyAct = ref('')
let timer = null

const ACTIONS = [
  { key: 'start', label: '启动', tip: (l) => `启动${l}（不影响其他链路）` },
  { key: 'stop', label: '停止', tip: (l) => `停止${l}（会让画面消失，需二次确认）` },
  { key: 'restart', label: '重启', tip: (l) => `重启${l}（画面会短暂中断后自动恢复，需二次确认）` }
]

/** 动作执行中的按钮文案 */
function actingLabel (key) {
  return ({ start: '启动中…', stop: '停止中…', restart: '重启中…' })[key] || '执行中…'
}

const t = (key) => (state.value.targets || {})[key] || {}
const lvl = (key) => t(key).level || 'off'

/** 状态徽标配色：与全站 pill 语义一致 */
function summaryPill (key) {
  const map = { ok: 'pill-ok', warn: 'pill-warn', off: 'pill-muted' }
  return map[lvl(key)] || 'pill-muted'
}

function detailOf (key) {
  const d = t(key)
  if (key === 'local') {
    return `进程 ${d.processes ?? '—'} · 编码器 ${d.gst ?? '—'} · `
      + `HLS ${d.hls_video1 ?? '—'}/${d.hls_video2 ?? '—'}`
  }
  return `unit ${d.unit ?? '—'} · 进程 ${d.processes ?? '—'} · `
    + `目标 ${d.target_tcp ? '可达' : '不可达'}`
}

async function load () {
  loading.value = true
  try {
    state.value = await getJson('/api/v1/video/service')
  } catch (e) {
    state.value = { ok: false, targets: {}, detail: String(e && e.message ? e.message : e) }
  } finally {
    loading.value = false
  }
}

async function act (target, action) {
  const label = t(target).label || target
  // 停止 / 重启都会让画面中断，统一走二次确认（原 window.confirm）
  if (action === 'stop' || action === 'restart') {
    const ok = await askConfirm({
      title: action === 'stop'
        ? `确认停止「${label}」？`
        : `确认重启「${label}」？`,
      message: action === 'stop'
        ? '停止后需要手动「启动」才会恢复。'
        : '重启期间画面会短暂中断，连接稳定后自动恢复。',
      detail: target === 'local'
        ? '这是喂控制台画面的那条 —— 操作期间本页画面会受影响，恢复后如仍黑屏可点「重新连接」。'
        : '这只是对外的转发，控制台画面不受影响。',
      confirmText: action === 'stop' ? '确认停止' : '确认重启',
      danger: action === 'stop'
    })
    if (!ok) return
  }
  busy.value = true
  busyAct.value = action
  err.value = ''
  try {
    const res = await postJson('/api/v1/video/service',
      { target, action, confirmed: action !== 'start' })
    if (res && res.ok) {
      state.value = { ok: true, targets: res.targets || {} }
    } else {
      err.value = `操作被拒：${(res && res.reason) || '未知'} ${(res && res.detail) || ''}`
    }
  } catch (e) {
    err.value = '请求失败：' + (e && e.message ? e.message : e)
  } finally {
    busy.value = false
    busyAct.value = ''
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
  margin-bottom: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-12);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}

.vsvc-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding-bottom: var(--sp-2);
  border-bottom: 1px solid var(--line);
}

.vsvc-title { font-weight: 600; font-size: var(--fs-13); color: var(--text); }

.vsvc-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  padding: var(--sp-2) 0;
  border-bottom: 1px solid var(--line);
}
.vsvc-row:last-of-type { border-bottom: 0; }

.vsvc-meta {
  flex: 1 1 320px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  min-width: 0;
}

.vsvc-label { font-weight: 600; color: var(--text); }

.vsvc-detail {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  font-size: var(--fs-11);
}

.vsvc-acts { flex: 0 0 auto; display: flex; gap: var(--sp-1); }

.vsvc-busy {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-11);
  color: var(--accent);
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  flex: 0 0 auto;
}
.dot.ok { color: var(--ok); box-shadow: 0 0 0 3px var(--ok-soft); }
.dot.warn { color: var(--warn); box-shadow: 0 0 0 3px var(--warn-soft); }
.dot.off { color: var(--muted); }

@media (max-width: 560px) {
  .vsvc-acts { width: 100%; }
}
</style>
