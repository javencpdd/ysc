<template>
  <!-- 指令报文记录（2026-10-17）：留下发出的原始字节帧 + 机器人是否响应。
       放在全局底部而不是某个标签页里 —— 相机页 / GPS 页 / 运动控制页发的指令
       都要能就地看到响应，切页才能看等于看不到。 -->
  <section class="pkt">
    <header class="pkt-head" @click="toggle" :aria-expanded="open">
      <span class="pkt-title">指令报文记录</span>
      <span v-if="lastBadge" class="pill" :class="lastBadge.cls">{{ lastBadge.text }}</span>
      <span v-else class="pill pill-muted">暂无</span>
      <span class="pkt-counts">
        <b class="ok num">{{ stats.ok || 0 }}</b> 成功 ·
        <b class="err num">{{ stats.error || 0 }}</b> 失败 ·
        <b class="nr num">{{ stats.no_response || 0 }}</b> 无响应 ·
        <b class="rj num">{{ stats.rejected || 0 }}</b> 被拒 ·
        <b class="sf num">{{ stats.send_failed || 0 }}</b> 未发出
      </span>
      <span class="spacer" />
      <button
        class="btn-sm btn-ghost"
        type="button"
        :title="open ? '收起报文列表（收起后停止轮询后端）' : '展开报文列表（开始每 1.5s 轮询）'"
        @click.stop="toggle"
      >{{ open ? '收起' : '展开' }}</button>
    </header>

    <div v-show="open" class="pkt-body">
      <p class="note" style="margin-bottom: var(--sp-2)">
        报文是<b>线上真实的字节</b>（含 16 字节帧头），点 hex 可整条复制。
        <b>「无响应」不代表车没执行</b> —— basic_server 对部分指令（如站立/趴下）执行了但并不回帧，
        这一列是"不知道"，不是"失败"。
      </p>

      <!-- 首次加载中的骨架提示：避免"展开后空白"被当成没数据 -->
      <div v-if="loading" class="empty-state">
        <span class="spinner" />
        <span class="empty-title">正在读取报文…</span>
      </div>

      <template v-else>
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
                <code
                  v-if="it.frame_hex"
                  :title="it.frame_hex"
                  @click="copy(it, it.frame_hex)"
                >{{ shortHex(it.frame_hex) }}</code>
                <span v-else class="dim">—</span>
                <button
                  v-if="it.frame_hex"
                  class="btn-sm btn-ghost"
                  type="button"
                  @click="expanded = expanded === it.seq ? 0 : it.seq"
                >{{ expanded === it.seq ? '收起详情' : '详情' }}</button>
                <span v-if="copiedSeq === it.seq" class="copied">已复制</span>
              </td>
              <td class="c-resp">
                <span class="pill" :class="respCls(it.resp.status)">
                  <span class="status-dot" :class="dotCls(it.resp.status)" />
                  {{ respText(it) }}
                </span>
                <span v-if="it.resp.latency_ms != null" class="lat">{{ it.resp.latency_ms }} ms</span>
              </td>
            </tr>
            <tr v-if="!items.length">
              <td colspan="4">
                <div class="empty-state">
                  <span class="empty-icon">∅</span>
                  <span class="empty-title">还没有指令记录</span>
                  <span class="empty-desc">在任意页面点一个控制按钮后，这里会留下发出的原始报文与车侧响应。</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </template>

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
const loading = ref(true)
const copiedSeq = ref(0)
let timer = null
let copyTimer = null

// 去掉 emoji：改用统一的状态点 + 文字，与全站徽标一致
const RESP_LABEL = {
  ok: '成功',
  error: '失败',
  no_response: '无响应',
  send_failed: '未发出',
  rejected: '被拒',
  pending: '等待中'
}

const RESP_DOT = {
  ok: 'ok',
  error: 'bad',
  no_response: 'warn',
  send_failed: 'warn',
  rejected: 'off',
  pending: 'off'
}

async function load () {
  try {
    const d = await getJson('/api/v1/control/packets?limit=60')
    items.value = d.items || []
    stats.value = d.stats || {}
  } catch {
    /* 后端不可用时静默：报文面板是诊断件，不该把主界面拖垮 */
  } finally {
    loading.value = false
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
onUnmounted(() => { stopPoll(); if (copyTimer) clearTimeout(copyTimer) })

// 只在展开时轮询（1.5s）—— 收起时不打后端，也不干扰主链路
watch(open, (v) => { v ? startPoll() : stopPoll() })

const lastItem = computed(() => items.value[0] || null)
const lastBadge = computed(() => {
  const it = lastItem.value
  if (!it) return null
  return {
    cls: respCls(it.resp.status),
    text: `${it.name} ${RESP_LABEL[it.resp.status] || it.resp.status}`
  }
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
  return { ok: 'pill-ok', error: 'pill-bad', no_response: 'pill-warn',
           send_failed: 'pill-warn', rejected: 'pill-muted', pending: 'pill-muted' }[st]
    || 'pill-muted'
}
function dotCls (st) { return RESP_DOT[st] || 'off' }
function respText (it) {
  const base = RESP_LABEL[it.resp.status] || it.resp.status
  if (it.resp.status === 'error') {
    return `${base}${it.resp.error_code != null ? ` (${it.resp.error_code})` : ''}`
  }
  if (it.resp.status === 'rejected') return `${base} ${it.resp.reason || ''}`.trim()
  if (it.resp.status === 'ok' && it.resp.error_code == null) return '已响应'
  return base
}
async function copy (it, hex) {
  try {
    await navigator.clipboard.writeText(hex)
    // 复制成功给一个可见反馈（原实现静默，用户无法确认到底复制了没）
    copiedSeq.value = it.seq
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copiedSeq.value = 0 }, 1500)
  } catch {
    /* 剪贴板不可用（非 HTTPS / 权限）时静默失败，用户还能手动选 */
  }
}
</script>

<style scoped>
.pkt {
  margin-top: var(--sp-4);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--panel);
  font-size: var(--fs-12);
  overflow: hidden;
}

.pkt-head {
  display: flex;
  gap: var(--sp-2);
  align-items: center;
  flex-wrap: wrap;
  padding: var(--sp-2) var(--sp-3);
  cursor: pointer;
  user-select: none;
  transition: background var(--t-fast);
}
.pkt-head:hover { background: var(--panel-2); }

.pkt-title { font-weight: 600; font-size: var(--fs-13); color: var(--text); }

.pkt-counts { color: var(--muted); }
.pkt-counts .ok { color: var(--ok); }
.pkt-counts .err { color: var(--danger); }
.pkt-counts .nr { color: var(--warn); }
.pkt-counts .sf { color: var(--warn); }
.pkt-counts .rj { color: var(--muted); }

.pkt-body { padding: 0 var(--sp-3) var(--sp-3); }

.pkt-table { width: 100%; border-collapse: collapse; }
.pkt-table th {
  padding: var(--sp-1) var(--sp-2);
  color: var(--muted);
  font-weight: 500;
  font-size: var(--fs-11);
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid var(--line);
}
.pkt-table td {
  padding: var(--sp-1) var(--sp-2);
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
.pkt-table tr.expanded td { background: var(--panel-2); }

.c-time {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
  width: 66px;
}
.c-cmd { width: 104px; }
.cmd-name { display: block; color: var(--text); }
.cmd-tc { color: var(--muted); font-size: var(--fs-11); }

.c-frame code {
  display: inline-block;
  max-width: 320px;
  overflow: hidden;
  color: var(--accent);
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
  cursor: copy;
  font-family: var(--ff-mono);
  font-size: var(--fs-11);
}
.c-frame code:hover { text-decoration: underline; }

.copied {
  margin-left: var(--sp-1);
  font-size: var(--fs-11);
  color: var(--ok);
}

.c-resp { width: 168px; white-space: nowrap; }
.lat {
  margin-left: var(--sp-1);
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  font-size: var(--fs-11);
}
.dim { color: var(--muted); }

.pkt-detail {
  max-height: 260px;
  margin: var(--sp-2) 0 0;
  padding: var(--sp-2) var(--sp-3);
  overflow: auto;
  font-family: var(--ff-mono);
  font-size: var(--fs-11);
  line-height: 1.5;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}

@media (max-width: 560px) {
  .c-frame code { max-width: 160px; }
}
</style>
