<script setup>
/**
 * PacketMonitor.vue
 * 可复用的报文监控组件（布局、交互、样式统一，差异全部由 props 注入）。
 *
 * 设计目的：多个标签页/多个数据源共用同一套报文列表视图，避免各自重复实现。
 *
 * ┌─ 组件接口 ────────────────────────────────────────────────────────┐
 * │ title / subtitle   标题与副标题                                    │
 * │ fetcher           必填。async () => Array<record>，数据源由外部注入 │
 * │ groups            必填。分组规则数组，见下                          │
 * │ mapper            可选。record -> 行数据（适配不同数据源的字段）     │
 * │ noteText          可选。record -> 类型文案                          │
 * │ limit / keep      拉取条数 / 前端累积条数                           │
 * │ intervalMs        轮询间隔（刷新策略）                              │
 * │ showPause         是否显示「暂停」开关                              │
 * │ parseData         是否显示「数据区解析格式」选择器                   │
 * └───────────────────────────────────────────────────────────────────┘
 *
 * groups 元素：
 *   {
 *     key:          'string'            分组唯一标识
 *     label:        'string'            分组标题
 *     tone:         'hb' | 'biz'        配色（仅两种预设，保证样式统一）
 *     match:        (record) => boolean 命中判定
 *     accumulate:   boolean             是否前端累积（避免被服务端环形缓冲淘汰）
 *     hideByDefault:boolean             是否默认隐藏（如高频心跳）
 *     rate:         boolean             是否估算并展示发送频率
 *   }
 *
 * 结构化展示（本组件的核心能力）：
 *   - 报文不再只给一串十六进制，而是拆成 code / 指令值 / type / data 四列；
 *   - 「十六进制预览」按 fields 分段着色，悬停可看该段含义；
 *   - 点任意行展开，看到逐字段表（偏移 / 长度 / 原始 hex / 解析值）；
 *   - 数据区可用下拉框切换解析格式（double / float / int32 / … / hex / ASCII）。
 *
 * 接入新数据源：只需提供一个新的 fetcher（+ 必要时 mapper/noteText）与 groups，
 * 组件内部的表格、开关、统计、轮询逻辑完全复用。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'

/** 数据区可选解析格式（小端，与协议一致） */
const DATA_FORMATS = [
  { key: 'auto', label: '自动' },
  { key: 'f64', label: 'double ×1' },
  { key: 'f32', label: 'float ×N' },
  { key: 'i32', label: 'int32 ×N' },
  { key: 'u32', label: 'uint32 ×N' },
  { key: 'i16', label: 'int16 ×N' },
  { key: 'u16', label: 'uint16 ×N' },
  { key: 'i8', label: 'int8 ×N' },
  { key: 'ascii', label: 'ASCII' },
  { key: 'hex', label: '原始 hex' }
]

/** 32 位值 -> 0xXXXXXXXX（全链路统一用十六进制呈现，不做十进制换算） */
function hex32(v) {
  if (v === undefined || v === null || v === '') return '—'
  return '0x' + (Number(v) >>> 0).toString(16).toUpperCase().padStart(8, '0')
}

const props = defineProps({
  title: { type: String, default: 'Packet Monitor' },
  subtitle: { type: String, default: '' },
  /** 数据源：async () => Array<record> */
  fetcher: { type: Function, required: true },
  /** 分组规则 */
  groups: { type: Array, required: true },
  /** record -> 行数据；默认适配控制审计记录（describe_packet 的输出） */
  mapper: {
    // 注意：defineProps 会被提升到 setup() 之外，这里不能引用模块内声明的
    // 函数（如 hex32），因此转换逻辑在 default 内部内联。
    type: Function,
    default: (r) => {
      const h32 = (v) =>
        v === undefined || v === null || v === ''
          ? '—'
          : '0x' + (Number(v) >>> 0).toString(16).toUpperCase().padStart(8, '0')
      return {
      key: String(r.ts),
      ts: Number(r.ts) || 0,
      time: r.ts ? new Date(r.ts * 1000).toLocaleTimeString('zh-CN', { hour12: false }) : '—',
      code: r.code_hex || '—',
      codeName: r.name || '',
      kind: r.kind || '',
      length: r.length ?? '—',
      type: h32(r.type),
      /**
       * 文档 1.1：该 uint32 在简单指令里是「指令值」，在复杂指令里是「数据长度」。
       * 一律按十六进制呈现（paramHex）；signedNote 仅在简单指令时给出有符号解读，
       * 因为轴指令会下发 -1、±6553 这类按 int32 解释的值。
       */
      param: h32(r.paramters_size),
      paramHex: h32(r.paramters_size),
      signedNote: r.param_meaning === 'value' && r.param_i32 !== undefined && r.param_i32 < 0
        ? '有符号 ' + r.param_i32
        : '',
      paramMeaning: r.param_meaning || 'value',
      data: r.data,
      dataHex: r.data_hex || '',
      dataViews: r.data_views || null,
      fields: r.fields || [],
      target: r.target || '—',
      hex: r.hex || ''
      }
    }
  },
  /** record -> 类型文案 */
  noteText: { type: Function, default: (r) => r.note || '—' },
  /** 前端累积时每组保留条数 */
  keep: { type: Number, default: 120 },
  /** 轮询间隔（ms） */
  intervalMs: { type: Number, default: 2000 },
  /** 是否显示暂停开关 */
  showPause: { type: Boolean, default: true },
  /** 是否显示数据区解析格式选择器 */
  parseData: { type: Boolean, default: true },
  /** 底部提示文案 */
  hint: { type: String, default: '' }
})

/** 分组 key -> 行数据数组 */
const buffers = ref({})
/** 被隐藏的分组 key */
const hidden = ref(new Set(props.groups.filter((g) => g.hideByDefault).map((g) => g.key)))
const paused = ref(false)
const errText = ref('')
const updatedAt = ref(0)
/** 当前展开的行 uid */
const expanded = ref('')
/** 数据区解析格式：默认保持十六进制原文（与报文一致），需要看数值时再切换 */
const dataFormat = ref('hex')

let timer = null

function rowsOf(key) {
  return buffers.value[key] || []
}

/** 估算发送频率（Hz）：按窗口内首末两条的时间差 */
function rateOf(key) {
  const rows = rowsOf(key)
  if (rows.length < 2) return null
  const newest = rows[0].ts
  const oldest = rows[rows.length - 1].ts
  const dt = newest - oldest
  if (!(dt > 0)) return null
  return ((rows.length - 1) / dt).toFixed(1)
}

async function refresh() {
  try {
    const items = (await props.fetcher()) || []
    const next = { ...buffers.value }

    for (const g of props.groups) {
      // uid 用「时间戳 + 序号 + 指令码」：同一毫秒内连发多条时 ts 会重复，
      // 直接拿 ts 当 key 会让 Vue 报重复 key、也让展开态串到别的行上。
      const rows = items.filter(g.match).map((r, i) => ({
        ...props.mapper(r),
        noteText: props.noteText(r),
        uid: `${r.ts}-${i}-${r.code}-${r.paramters_size}`
      }))

      if (g.accumulate && rows.length) {
        // 累积：按 key 去重后并入，服务端缓冲淘汰不影响这里
        const seen = new Set((next[g.key] || []).map((r) => r.key))
        const add = rows.filter((r) => !seen.has(r.key))
        next[g.key] = add.length ? [...add, ...(next[g.key] || [])].slice(0, props.keep) : next[g.key] || []
      } else {
        next[g.key] = rows
      }
    }

    buffers.value = next
    updatedAt.value = Date.now()
    errText.value = ''
  } catch (err) {
    errText.value = err.message || '获取记录失败'
  }
}

function toggleGroup(key) {
  const s = new Set(hidden.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  hidden.value = s
}

function toggleRow(uid) {
  expanded.value = expanded.value === uid ? '' : uid
}

function clearGroup(key) {
  buffers.value = { ...buffers.value, [key]: [] }
  expanded.value = ''
}

const visibleGroups = computed(() => props.groups.filter((g) => !hidden.value.has(g.key)))

const updatedText = computed(() =>
  updatedAt.value ? new Date(updatedAt.value).toLocaleTimeString('zh-CN', { hour12: false }) : '—'
)

// ------------------------------------------------------------------
// 结构化解析
// ------------------------------------------------------------------

/** hex 串 -> 字节数组（非法字符直接忽略，长度不足返回空） */
function hexToBytes(hex) {
  const clean = String(hex || '').replace(/[^0-9a-fA-F]/g, '')
  if (!clean.length || clean.length % 2 !== 0) return new Uint8Array(0)
  const out = new Uint8Array(clean.length / 2)
  for (let i = 0; i < out.length; i++) out[i] = parseInt(clean.substr(i * 2, 2), 16)
  return out
}

function fmtNum(v) {
  if (!Number.isFinite(v)) return '—'
  return Math.abs(v) >= 1e-4 && Math.abs(v) < 1e6 ? String(Number(v.toFixed(6))) : v.toExponential(4)
}

function fmtList(list) {
  if (!list || !list.length) return '—'
  return list.map(fmtNum).join(', ')
}

/** 按指定格式解码数据区 */
function decodeBody(hex, fmt, type) {
  const bytes = hexToBytes(hex)
  if (!bytes.length) return '—'
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const le = true // 协议为小端
  const n32 = Math.floor(bytes.length / 4)
  const n16 = Math.floor(bytes.length / 2)

  let f = fmt
  if (f === 'auto') {
    // 默认不换算：复杂指令（type=1）按协议是 double，但界面以十六进制为准
    f = 'hex'
  }

  switch (f) {
    case 'f64':
      return bytes.length >= 8 ? fmtNum(view.getFloat64(0, le)) : '长度不足 8B'
    case 'f32': {
      const n = Math.floor(bytes.length / 4)
      if (!n) return '长度不足 4B'
      const arr = []
      for (let i = 0; i < n; i++) arr.push(view.getFloat32(i * 4, le))
      return fmtList(arr)
    }
    case 'i32': {
      if (!n32) return '长度不足 4B'
      const arr = []
      for (let i = 0; i < n32; i++) arr.push(view.getInt32(i * 4, le))
      return fmtList(arr)
    }
    case 'u32': {
      if (!n32) return '长度不足 4B'
      const arr = []
      for (let i = 0; i < n32; i++) arr.push(view.getUint32(i * 4, le))
      return fmtList(arr)
    }
    case 'i16': {
      if (!n16) return '长度不足 2B'
      const arr = []
      for (let i = 0; i < n16; i++) arr.push(view.getInt16(i * 2, le))
      return fmtList(arr)
    }
    case 'u16': {
      if (!n16) return '长度不足 2B'
      const arr = []
      for (let i = 0; i < n16; i++) arr.push(view.getUint16(i * 2, le))
      return fmtList(arr)
    }
    case 'i8': {
      const arr = []
      for (let i = 0; i < bytes.length; i++) arr.push(view.getInt8(i))
      return fmtList(arr)
    }
    case 'ascii':
      return Array.from(bytes)
        .map((b) => (b >= 0x20 && b <= 0x7e ? String.fromCharCode(b) : '.'))
        .join('')
    case 'hex':
    default:
      return hex ? '0x' + String(hex).toUpperCase() : '—'
  }
}

/** 列表里 data 列的显示值（默认纯十六进制） */
function dataText(row) {
  if (!row.dataHex) return '—'
  return decodeBody(row.dataHex, dataFormat.value, row.type)
}

/** 把整条 hex 按 fields 切成若干段，用于分段着色与悬停释义 */
function segmentsOf(row) {
  const hex = row.hex || ''
  if (!row.fields || !row.fields.length) return [{ hex, label: '原始数据（无结构化字段）', idx: 0 }]
  return row.fields.map((f, i) => ({
    idx: i,
    hex: hex.substr(f.offset * 2, f.size * 2),
    label: `${f.label}｜偏移 ${f.offset}B · ${f.size}B｜值 ${f.value || '—'}`
  }))
}

/** 指令值列的悬停释义：说明这个 uint32 在该报文里到底是什么 */
function paramTitle(row) {
  if (row.paramMeaning === 'size') return '复杂指令：该字段为数据长度（字节）'
  if (row.paramMeaning === 'joystick') return '手柄帧：该偏移属于手柄协议，非命令帧'
  return row.signedNote ? `简单指令：即指令值；${row.signedNote}` : '简单指令：该字段即指令值'
}

/** 详情面板里的数据区其他解释（十六进制已是默认，这里只作可选换算） */
function viewsOf(row) {
  const v = row.dataViews
  const out = []
  if (!v || !v.length) return out
  if (v.f64 !== undefined) out.push(['double', fmtNum(v.f64)])
  if (v.f32x2) out.push(['float ×2', fmtList(v.f32x2)])
  if (v.i32 && v.i32.length) out.push(['int32 ×N', fmtList(v.i32)])
  if (v.u32 && v.u32.length) out.push(['uint32 ×N', fmtList(v.u32)])
  if (v.i16 && v.i16.length) out.push(['int16 ×N', fmtList(v.i16)])
  if (v.u16 && v.u16.length) out.push(['uint16 ×N', fmtList(v.u16)])
  return out
}

onMounted(() => {
  refresh()
  timer = setInterval(() => {
    if (!paused.value) refresh()
  }, props.intervalMs)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <section class="card">
    <div class="card-title">
      <span>{{ title }}</span>
      <span class="actions">
        <span v-if="subtitle" class="sub">{{ subtitle }}</span>
        <select
          v-if="parseData"
          v-model="dataFormat"
          class="sel"
          title="数据区（第 12 字节起）按什么类型解析"
        >
          <option v-for="f in DATA_FORMATS" :key="f.key" :value="f.key">
            data: {{ f.label }}
          </option>
        </select>
        <label v-for="g in groups" :key="g.key" class="switch" :class="g.tone">
          <input type="checkbox" :checked="!hidden.has(g.key)" @change="toggleGroup(g.key)" />
          {{ g.label }}
        </label>
        <label v-if="showPause" class="switch">
          <input v-model="paused" type="checkbox" />
          暂停
        </label>
        <button class="btn" @click="refresh">刷新</button>
        <button
          v-for="g in groups.filter((x) => x.accumulate)"
          :key="`c-${g.key}`"
          class="btn ghost"
          @click="clearGroup(g.key)"
        >
          清空{{ g.label }}
        </button>
      </span>
    </div>

    <div class="stats">
      <span v-for="g in groups" :key="`s-${g.key}`" class="stat" :class="g.tone">
        {{ g.label }} <b>{{ rowsOf(g.key).length }}</b> 条
        <em v-if="g.rate && rateOf(g.key)">≈{{ rateOf(g.key) }} Hz</em>
        <em v-else-if="g.rate">窗口内</em>
        <em v-else-if="g.accumulate">前端累积</em>
      </span>
      <span class="stat time">更新于 {{ updatedText }}</span>
    </div>

    <div v-if="errText" class="notice bad">{{ errText }}</div>

    <div class="legend">
      <span class="lg s0">code</span>
      <span class="lg s1">{{ '指令值 / 长度' }}</span>
      <span class="lg s2">type</span>
      <span class="lg s3">data</span>
      <em>十六进制按字段分段；点击任意行展开逐字段解析</em>
    </div>

    <template v-for="g in visibleGroups" :key="`v-${g.key}`">
      <div class="sub-title" :class="g.tone">
        {{ g.label }}<small>{{ rowsOf(g.key).length }} 条</small>
      </div>

      <div v-if="!rowsOf(g.key).length" class="empty">暂无记录。</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width: 26px"></th>
              <th style="width: 84px">时间</th>
              <th style="width: 96px">类型</th>
              <th style="width: 104px">指令码</th>
              <th style="width: 96px">指令值 / 长度</th>
              <th style="width: 86px">type</th>
              <th style="width: 150px">data</th>
              <th>十六进制预览（分段）</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in rowsOf(g.key)" :key="row.uid">
              <tr
                class="row-main"
                :class="{ 'row-hb': g.tone === 'hb', 'row-open': expanded === row.uid }"
                @click="toggleRow(row.uid)"
              >
                <td class="mono caret">{{ expanded === row.uid ? '▾' : '▸' }}</td>
                <td class="mono">{{ row.time }}</td>
                <td>{{ row.noteText }}</td>
                <td class="mono code">
                  <div>{{ row.code }}</div>
                  <div v-if="row.codeName" class="code-name">{{ row.codeName }}</div>
                </td>
                <td class="mono">
                  <span :title="paramTitle(row)">{{ row.param }}</span>
                  <em v-if="row.paramMeaning === 'size'" class="tag">len</em>
                </td>
                <td class="mono">{{ row.type }}</td>
                <td class="mono data" :title="dataText(row)">{{ dataText(row) }}</td>
                <td class="mono hex">
                  <span
                    v-for="seg in segmentsOf(row)"
                    :key="seg.idx"
                    class="seg"
                    :class="'s' + seg.idx"
                    :title="seg.label"
                  >{{ seg.hex }}</span>
                </td>
              </tr>

              <tr v-if="expanded === row.uid" class="row-detail">
                <td colspan="8">
                  <div class="detail">
                    <div class="detail-col">
                      <h4>结构化字段</h4>
                      <table class="mini">
                        <thead>
                          <tr>
                            <th>字段</th>
                            <th style="width: 74px">偏移·长度</th>
                            <th style="width: 150px">原始 hex</th>
                            <th style="width: 130px">值（hex）</th>
                            <th>说明</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="f in row.fields" :key="f.name">
                            <td>
                              {{ f.label }}
                              <em class="fname">{{ f.name }}</em>
                            </td>
                            <td class="mono">{{ f.offset }}B · {{ f.size }}B</td>
                            <td class="mono">{{ f.hex }}</td>
                            <td class="mono val">{{ f.value || '—' }}</td>
                            <td class="dim-note">{{ f.note || '' }}</td>
                          </tr>
                          <tr v-if="!row.fields.length">
                            <td colspan="5" class="dim">该报文未提供结构化字段</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    <div class="detail-col narrow">
                      <h4>数据区（默认十六进制）</h4>
                      <div class="kv">
                        <span>hex</span>
                        <b class="mono">{{ row.dataHex ? '0x' + row.dataHex.toUpperCase() : '—' }}</b>
                      </div>
                      <template v-if="viewsOf(row).length">
                        <div class="kv alt">
                          <span>可选换算</span>
                          <b class="dim-inline">下方为同一段字节的其他解释</b>
                        </div>
                        <div v-for="v in viewsOf(row)" :key="v[0]" class="kv">
                          <span>{{ v[0] }}</span>
                          <b class="mono">{{ v[1] }}</b>
                        </div>
                      </template>
                      <div v-else-if="!row.dataHex" class="dim">无数据区（简单指令）</div>
                      <div class="kv"><span>报文类型</span><b>{{ row.kind || '—' }}</b></div>
                      <div class="kv"><span>总长度</span><b class="mono">{{ row.length }} B</b></div>
                      <div class="kv"><span>目标</span><b class="mono">{{ row.target }}</b></div>
                      <div class="kv"><span>完整 hex</span></div>
                      <div class="full-hex mono">{{ row.hex }}</div>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </template>

    <div v-if="hint" class="hint">{{ hint }}</div>
  </section>
</template>

<style scoped>
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.switch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  font-weight: 400;
  color: var(--text-sub);
}

/* 中性描边为默认（与全局按钮规范一致），蓝色只用于选中态 */
.btn {
  padding: 3px 10px;
  font-size: 12px;
  color: #334155;
  background: #ffffff;
  border: 1px solid #dbe2ea;
  border-radius: 6px;
  cursor: pointer;
}

.btn:hover { background: #f1f5f9; border-color: #cbd5e1; }

.btn.ghost {
  color: #475569;
  background: var(--chip-bg);
  border: 1px solid #dfe5ec;
}

.btn.ghost:hover { background: #e8edf4; }

/* 解析格式下拉：与按钮同高，保持工具栏视觉一致 */
.sel {
  padding: 3px 6px;
  font-size: 11.5px;
  color: #334155;
  background: #ffffff;
  border: 1px solid #dbe2ea;
  border-radius: 6px;
  cursor: pointer;
}

.stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.stat {
  padding: 5px 10px;
  font-size: 11.5px;
  color: #334155;
  background: #f8fafc;
  border: 1px solid #e6ecf3;
  border-radius: 8px;
}

.stat b { font-size: 13px; }
.stat em { margin-left: 6px; font-style: normal; color: #94a3b8; }
.stat.hb { color: #166534; background: #f0fdf4; border-color: #bbf7d0; }
.stat.biz { color: #1e40af; background: #eff6ff; border-color: #bfdbfe; }
.stat.time { color: #64748b; }

/* 分段着色图例 */
.legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 11px;
  color: #94a3b8;
}

.legend em { margin-left: 6px; font-style: normal; }

.lg {
  padding: 1px 7px;
  border-radius: 4px;
  color: #334155;
}

.sub-title {
  margin: 12px 0 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: #334155;
}

.sub-title small {
  margin-left: 8px;
  font-size: 11px;
  font-weight: 400;
  color: #94a3b8;
}

.sub-title.hb { color: #166534; }

.table-wrap { max-height: 320px; overflow: auto; }

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

th {
  position: sticky;
  top: 0;
  padding: 8px 10px;
  text-align: left;
  font-weight: 600;
  color: var(--text-sub);
  background: #f8fafc;
  border-bottom: 1px solid #e6ecf3;
}

td {
  padding: 7px 10px;
  color: #334155;
  border-bottom: 1px solid #f1f5f9;
  white-space: nowrap;
}

.row-main { cursor: pointer; }
.row-main:hover { background: #f8fafc; }
.row-open { background: #f1f5f9; }
.row-hb { background: #f8fdf9; }
.row-hb.row-open { background: #eef8f1; }

.caret { color: #94a3b8; }

.hex {
  width: 100%;
  max-width: 640px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #64748b;
  white-space: nowrap;
}

/* 四段交替底色：code / 指令值 / type / data */
.seg { padding: 1px 2px; border-radius: 3px; }
.seg.s0 { background: #e0e7ff; color: #3730a3; }
.seg.s1 { background: #dcfce7; color: #166534; }
.seg.s2 { background: #fef3c7; color: #92400e; }
.seg.s3 { background: #ffe4e6; color: #9f1239; }

.lg.s0 { background: #e0e7ff; color: #3730a3; }
.lg.s1 { background: #dcfce7; color: #166534; }
.lg.s2 { background: #fef3c7; color: #92400e; }
.lg.s3 { background: #ffe4e6; color: #9f1239; }

.code { color: var(--accent); font-weight: 600; }

.code-name {
  font-size: 10.5px;
  font-weight: 400;
  color: #64748b;
}

.data {
  max-width: 116px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag {
  margin-left: 4px;
  padding: 0 4px;
  font-size: 10px;
  font-style: normal;
  color: #92400e;
  background: #fef3c7;
  border-radius: 3px;
}

/* 展开详情 */
.row-detail td { padding: 0; background: #fbfcfe; white-space: normal; }
.row-detail:hover { background: #fbfcfe; }

.detail {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  padding: 12px 16px 14px;
  border-bottom: 1px solid #e6ecf3;
}

.detail-col { flex: 1 1 380px; min-width: 280px; }
.detail-col.narrow { flex: 0 1 300px; min-width: 240px; }

.detail h4 {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}

.mini {
  font-size: 11.5px;
  border: 1px solid #e6ecf3;
  border-radius: 6px;
  overflow: hidden;
}

.mini th {
  position: static;
  padding: 5px 8px;
  font-size: 11px;
  background: #f8fafc;
}

.mini td {
  padding: 5px 8px;
  border-bottom: 1px solid #f1f5f9;
  white-space: nowrap;
}

.fname {
  margin-left: 6px;
  font-size: 10px;
  font-style: normal;
  color: #94a3b8;
}

.kv {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 3px 0;
  font-size: 11.5px;
  color: #64748b;
  border-bottom: 1px dashed #eef2f7;
}

.kv span { flex: 0 0 84px; }
.kv b { color: #334155; font-weight: 500; word-break: break-all; }

.full-hex {
  padding: 6px 8px;
  margin-top: 4px;
  font-size: 11px;
  color: #475569;
  background: #f1f5f9;
  border-radius: 6px;
  word-break: break-all;
}

.dim { padding: 6px 0; font-size: 11.5px; color: #94a3b8; }
.dim-note { font-size: 11px; color: #94a3b8; white-space: normal; }
.dim-inline { font-size: 11px; font-weight: 400; color: #94a3b8; }
.val { color: #3730a3; }
.kv.alt { border-bottom-style: solid; }
.kv.alt span { color: #94a3b8; }

.empty { padding: 18px 0; text-align: center; color: #94a3b8; }

.notice { padding: 7px 12px; margin-bottom: 10px; font-size: 12.5px; border-radius: 6px; }
.notice.bad { color: #991b1b; background: #fee2e2; }

.hint { margin-top: 10px; font-size: 11.5px; color: #94a3b8; line-height: 1.6; }
</style>
