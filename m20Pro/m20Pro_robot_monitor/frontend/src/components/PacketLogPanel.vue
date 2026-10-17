<template>
  <!-- 指令报文记录（2026-10-17）：留下发出的原始字节帧 + 机器人是否响应。
       放在全局底部而不是某个标签页里 —— 相机页 / GPS 页 / 运动控制页发的指令
       都要能就地看到响应，切页才能看等于看不到。 -->
  <section class="pkt">
    <header class="pkt-head" @click="toggle">
      <span class="pkt-title">指令报文记录</span>
      <span v-if="lastBadge" class="pkt-badge" :class="lastBadge.cls">{{ lastBadge.text }}</span>
      <span v-else class="pkt-badge dim">暂无</span>
      <span class="pkt-counts">
        <b class="ok">{{ stats.ok || 0 }}</b> 成功 ·
        <b class="err">{{ stats.error || 0 }}</b> 失败 ·
        <b class="nr">{{ stats.no_response || 0 }}</b> 无响应 ·
        <b class="rj">{{ stats.rejected || 0 }}</b> 被拒
      </span>
      <span class="pkt-spacer"></span>
      <button class="pkt-toggle" type="button">{{ open ? '收起 ▲' : '展开 ▼' }}</button>
    </header>

    <div v-show="open" class="pkt-body">
      <p class="pkt-note">
        报文是<b>线上真实的字节</b>（含 16 字节帧头），点 hex 可整条复制。
        <b>「无响应」不代表车没执行</b> —— basic_server 对部分指令（如站立/趴下）执行了但并不回帧，
        这一列是"不知道"，不是"失败"。
      </p>

      <table class="pkt-table">
        <thead>
          <tr>
            <th class="c-time">时间</th>
            <th class="c-cmd">指令</th>
            <th class="c-frame">报文（hex）</th>
            <th class="c-resp">响应</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.seq" :class="{ expanded: expanded === it.seq }">
            <td class="c-time">{{ hhmmss(it.ts) }}</td>
            <td class="c-cmd">
              <span class="cmd-name">{{ it.name }}</span>
              <span v-if="it.type != null" class="cmd-tc">{{ it.type }}/{{ it.command }}</span>
              <span v-else class="cmd-tc dim">未生成</span>
            </td>
            <td class="c-frame">
              <code v-if="it.frame_hex" :title="it.frame_hex" @click="copy(it.frame_hex)">
                {{ shortHex(it.frame_hex) }}
              </code>
              <span v-else class="dim">—</span>
              <button v-if="it.frame_hex" class="mini" type="button"
                      @click="expanded = expanded === it.seq ? 0 : it.seq">
                {{ expanded === it.seq ? '收起' : '详情' }}
              </button>
            </td>
            <td class="c-resp">
              <span class="resp" :class="respCls(it.resp.status)">{{ respText(it) }}</span>
              <span v-if="it.resp.latency_ms != null" class="lat">{{ it.resp.latency_ms }} ms</span>
            </td>
          </tr>
          <tr v-if="!items.length">
            <td colspan="4" class="empty">还没有指令记录 —— 在任意页面点一个控制按钮试试</td>
          </tr>
        </tbody>
      </table>

      <!-- 展开详情：完整 JSON（发出 + 响应）-->
      <pre v-if="detail" class="pkt-detail">{{ detail }}</pre>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getJson } from '../api/index.js'

const open = ref(false)
const items = ref([])
const stats = ref({})
const expanded = ref(0)
let timer = null

const RESP_LABEL = {
  ok: '✅ 成功',
  error: '❌ 失败',
  no_response: '⏳ 无响应',
  send_failed: '🚫 未发出',
  rejected: '⛔ 被拒',
  pending: '⋯ 等待中'
}

async function load () {
  try {
    const d = await getJson('/api/v1/control/packets?limit=60')
    items.value = d.items || []
    stats.value = d.stats || {}
  } catch {
    /* 后端不可用时静默：报文面板是诊断件，不该把主界面拖垮 */
  }
}

function toggle () { open.value = !open.value }

// 只在展开时轮询（1.5s）—— 收起时不打后端，也不干扰主链路
function startPoll () {
  if (timer) return
  load()
  timer = setInterval(load, 1500)
}
function stopPoll () {
  if (timer) { clearInterval(timer); timer = null }
}

onMounted(() => { load() })
onUnmounted(stopPoll)

// 只在展开时轮询（1.5s）—— 收起时不打后端，也不干扰主链路
watch(open, (v) => { v ? startPoll() : stopPoll() })

const lastItem = computed(() => items.value[0] || null)
const lastBadge = computed(() => {
  const it = lastItem.value
  if (!it) return null
  return { cls: respCls(it.resp.status), text: `${it.name} ${RESP_LABEL[it.resp.status] || it.resp.status}` }
})

const detail = computed(() => {
  const it = items.value.find((x) => x.seq === expanded.value)
  if (!it) return ''
  const out = {
    指令: it.name,
    'Type/Command': it.type != null ? `${it.type}/${it.command}` : '（未生成报文）',
    '发出 Items': it.items,
    '报文 hex': it.frame_hex,
    '报文长度': it.frame_len ? `${it.frame_len} 字节` : '—',
    响应: it.resp
  }
  if (it.resp && it.resp.detail) out['拒绝原因'] = it.resp.detail
  return JSON.stringify(out, null, 2)
})

function hhmmss (ts) {
  const d = new Date(ts * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
function shortHex (hex) {
  // 帧头 16 字节 = 32 hex 字符；只露头尾，中间省略，title 给全量
  if (hex.length <= 72) return hex
  return `${hex.slice(0, 40)}…${hex.slice(-24)}`
}
function respCls (st) {
  return { ok: 'ok', error: 'err', no_response: 'nr',
           send_failed: 'sf', rejected: 'rj', pending: 'pd' }[st] || 'pd'
}
function respText (it) {
  const base = RESP_LABEL[it.resp.status] || it.resp.status
  if (it.resp.status === 'error') {
    return `${base}${it.resp.error_code != null ? ` (${it.resp.error_code})` : ''}`
  }
  if (it.resp.status === 'rejected') return `${base} ${it.resp.reason || ''}`.trim()
  if (it.resp.status === 'ok' && it.resp.error_code == null) return '✅ 已响应'
  return base
}
async function copy (hex) {
  try {
    await navigator.clipboard.writeText(hex)
  } catch {
    /* 剪贴板不可用（非 HTTPS / 权限）时静默失败，用户还能手动选 */
  }
}
</script>

<style scoped>
.pkt {
  margin-top: 14px;
  border: 1px solid var(--border, #d8dce3);
  border-radius: 8px;
  background: var(--panel-2, #f7f8fa);
  font-size: 12px;
}
.pkt-head {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 7px 10px;
  cursor: pointer;
  user-select: none;
}
.pkt-title { font-weight: 600; }
.pkt-spacer { flex: 1 1 auto; }
.pkt-badge { padding: 1px 8px; border: 1px solid currentColor; border-radius: 10px; }
.pkt-badge.ok { color: var(--ok, #2e9e5b); }
.pkt-badge.err { color: var(--danger, #d0453b); }
.pkt-badge.nr { color: var(--warn, #c47f17); }
.pkt-badge.rj { color: var(--muted, #888); }
.pkt-badge.dim { color: var(--muted, #888); }
.pkt-counts { color: var(--muted, #888); }
.pkt-counts .ok { color: var(--ok, #2e9e5b); }
.pkt-counts .err { color: var(--danger, #d0453b); }
.pkt-counts .nr { color: var(--warn, #c47f17); }
.pkt-toggle {
  padding: 1px 8px;
  font-family: inherit;
  color: var(--muted, #888);
  background: transparent;
  border: 1px solid var(--line);
  border-radius: 4px;
}
.pkt-body { padding: 0 10px 10px; }
.pkt-note { margin: 0 0 8px; color: var(--muted, #888); line-height: 1.6; }
.pkt-table { width: 100%; border-collapse: collapse; }
.pkt-table th {
  padding: 4px 6px;
  color: var(--muted, #888);
  font-weight: 500;
  text-align: left;
  border-bottom: 1px solid var(--border, #d8dce3);
}
.pkt-table td { padding: 4px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }
.pkt-table tr.expanded td { background: var(--panel, #fff); }
.c-time { white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--muted, #888); width: 62px; }
.c-cmd { width: 96px; }
.cmd-name { display: block; }
.cmd-tc { color: var(--muted, #888); font-size: 11px; }
.c-frame code {
  display: inline-block;
  max-width: 340px;
  overflow: hidden;
  color: var(--accent, #2f6fed);
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
  cursor: copy;
  font-size: 11px;
}
.mini {
  margin-left: 6px;
  padding: 0 6px;
  font-size: 11px;
  font-family: inherit;
  color: var(--muted, #888);
  background: transparent;
  border: 1px solid var(--line);
  border-radius: 4px;
}
.c-resp { width: 150px; white-space: nowrap; }
.resp { font-weight: 600; }
.resp.ok { color: var(--ok, #2e9e5b); }
.resp.err { color: var(--danger, #d0453b); }
.resp.nr { color: var(--warn, #c47f17); }
.resp.sf { color: var(--warn, #c47f17); }
.resp.rj { color: var(--muted, #888); }
.resp.pd { color: var(--muted, #888); }
.lat { margin-left: 6px; color: var(--muted, #888); font-variant-numeric: tabular-nums; }
.empty { padding: 12px 6px; color: var(--muted, #888); text-align: center; }
.dim { color: var(--muted, #888); }
.pkt-detail {
  max-height: 260px;
  margin: 8px 0 0;
  padding: 8px 10px;
  overflow: auto;
  font-size: 11px;
  line-height: 1.5;
  background: var(--panel, #fff);
  border: 1px solid var(--border, #d8dce3);
  border-radius: 6px;
}
</style>
