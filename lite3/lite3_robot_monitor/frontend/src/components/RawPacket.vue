<script setup>
/**
 * RawPacket.vue
 * 原始 UDP 报文查看：来源 IP、长度、消息码与十六进制预览。
 */
import { computed } from 'vue'

const props = defineProps({
  /** 原始报文摘要数组（来自 GET /api/raw） */
  packets: { type: Array, default: () => [] }
})
const emit = defineEmits(['refresh', 'clear'])

/** 表格行数据：补充格式化字段 */
const rows = computed(() =>
  props.packets.map((p) => ({
    ...p,
    time: p.received_at ? new Date(p.received_at * 1000).toLocaleTimeString('zh-CN', { hour12: false }) : '--'
  }))
)
</script>

<template>
  <section class="card">
    <div class="card-title">
      <span>Raw UDP Packets</span>
      <span class="actions">
        <span class="sub">{{ rows.length }} 条</span>
        <button class="btn" @click="emit('refresh')">刷新</button>
        <button class="btn ghost" @click="emit('clear')">清空</button>
      </span>
    </div>

    <div v-if="!rows.length" class="empty">暂无原始报文，请确认 Lite3 已向本机 UDP 端口发送数据。</div>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th style="width: 92px">时间</th>
            <th style="width: 76px">消息码</th>
            <th style="width: 70px">长度</th>
            <th style="width: 140px">来源</th>
            <th>十六进制预览</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in rows" :key="idx">
            <td class="mono">{{ row.time }}</td>
            <td class="mono code">{{ row.code }}</td>
            <td class="mono">{{ row.length }}</td>
            <td class="mono">{{ row.source_ip }}:{{ row.source_port }}</td>
            <td class="mono hex">{{ row.hex_preview }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 中性描边为默认（与全局按钮规范一致） */
.btn {
  padding: 3px 10px;
  font-size: 12px;
  color: #334155;
  background: #ffffff;
  border: 1px solid #dbe2ea;
  border-radius: 6px;
  cursor: pointer;
}

.btn:hover {
  background: #f1f5f9;
  border-color: #cbd5e1;
}

.btn.ghost {
  color: #475569;
  background: var(--chip-bg);
  border: 1px solid #dfe5ec;
}

.table-wrap {
  max-height: 260px;
  overflow: auto;
}

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

.hex {
  width: 100%;
  max-width: 640px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #64748b;
}

.code {
  color: var(--accent);
  font-weight: 600;
}

.empty {
  padding: 24px 0;
  text-align: center;
  color: #94a3b8;
}
</style>
