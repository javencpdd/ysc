<script setup>
/**
 * SentPacket.vue
 * 发包监控的**预置配置**（薄封装）：只提供数据源与分组规则，
 * 布局 / 表格 / 开关 / 统计 / 轮询全部复用 PacketMonitor。
 *
 * 这样多个标签页可以各自传入不同的 limit / intervalMs / 是否展开心跳,
 * 而不需要各自实现一套报文列表。
 */
import { computed } from 'vue'
import PacketMonitor from './PacketMonitor.vue'
import { fetchControlAudit } from '../api/index.js'

const props = defineProps({
  /** 每次拉取条数（服务端审计为 200 条环形缓冲） */
  limit: { type: Number, default: 200 },
  /** 轮询间隔（ms） */
  intervalMs: { type: Number, default: 2000 },
  /** 业务包前端累积条数 */
  keep: { type: Number, default: 120 },
  /** 标题 */
  title: { type: String, default: 'Sent UDP Packets' },
  /** 心跳包是否默认隐藏（4Hz 高频，默认隐藏以免刷屏） */
  hideHeartbeat: { type: Boolean, default: true }
})

/** 心跳 note 均以 heartbeat 开头：heartbeat / heartbeat-velocity / heartbeat-stop / heartbeat-exit */
function isHeartbeat(note) {
  return typeof note === 'string' && note.startsWith('heartbeat')
}

const NOTE_TEXT = {
  heartbeat: '心跳',
  'heartbeat-velocity': '心跳+速度',
  'heartbeat-stop': '心跳停止',
  'heartbeat-exit': '心跳退出',
  velocity: '速度指令',
  custom: '自定义指令',
  raw: '原始报文',
  'estop-velocity': '急停零速',
  'estop-soft': '软急停'
}

function noteTextOf(r) {
  const note = r.note || ''
  if (NOTE_TEXT[note]) return NOTE_TEXT[note]
  if (note.startsWith('preset:')) return `预置 ${note.slice(7)}`
  return note || '—'
}

const groups = computed(() => [
  {
    key: 'heartbeat',
    label: '心跳包',
    tone: 'hb',
    match: (r) => isHeartbeat(r.note),
    accumulate: false,
    hideByDefault: props.hideHeartbeat,
    rate: true
  },
  {
    key: 'business',
    label: '业务包',
    tone: 'biz',
    match: (r) => !isHeartbeat(r.note),
    accumulate: true,
    hideByDefault: false,
    rate: false
  }
])

/** 数据源：控制通道审计记录 */
async function fetcher() {
  const data = await fetchControlAudit(props.limit)
  return data?.items || []
}

const HINT =
  '心跳以 0.25s 周期（4Hz）发送，服务端审计缓冲为 200 条，开启后约 50 秒即被填满，' +
  '这也是业务指令容易被冲掉的原因；业务表在前端累积，不受此限制。'
</script>

<template>
  <PacketMonitor
    :title="title"
    subtitle="发包监控"
    :fetcher="fetcher"
    :groups="groups"
    :note-text="noteTextOf"
    :keep="keep"
    :interval-ms="intervalMs"
    :hint="HINT"
  />
</template>
