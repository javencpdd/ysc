<template>
  <div class="panel span-all" :class="{ stale: isStale('motion') }">
    <h3>
      运控状态
      <small>（1002/4 · 10Hz · 轮足 16 关节）</small>
    </h3>

    <div class="grid" style="margin-bottom: var(--sp-3)">
      <div class="kv"><span>姿态 R/P/Y</span>
        <span>{{ fmt(m.roll) }} / {{ fmt(m.pitch) }} / {{ fmt(m.yaw) }}</span></div>
      <div class="kv"><span>线速度 X/Y</span><span>{{ fmt(m.linear_x) }} / {{ fmt(m.linear_y) }}</span></div>
      <div class="kv"><span>角速度 Z</span><span>{{ fmt(m.omega_z) }}</span></div>
      <div class="kv"><span>机体高度</span><span>{{ fmt(m.height) }}</span></div>
      <div class="kv"><span>剩余里程</span><span>{{ fmt(m.remain_mile) }}</span></div>
    </div>

    <!-- 轮足结构：4 腿 × (hip_x, hip_y, knee, wheel)，与 lite3 的 12 关节不同 -->
    <div v-if="joints.length">
      <div class="block-title" style="margin-bottom: var(--sp-2)">关节角度</div>
      <table>
        <thead>
          <tr><th>关节</th><th>角度</th><th>关节</th><th>角度</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td>{{ row[0].name }}</td><td class="num">{{ fmt(row[0].value) }}</td>
            <td>{{ row[1].name }}</td><td class="num">{{ fmt(row[1].value) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 空状态：说清"没数据"与"数据为 0"的区别 -->
    <div v-else class="empty-state">
      <span class="empty-icon">∅</span>
      <span class="empty-title">暂无关节数据</span>
      <span class="empty-desc">尚未收到运控状态帧（1002/4）。机器人休眠或链路中断时都会是空的。</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  topic: { type: Function, required: true },
  isStale: { type: Function, required: true }
})

const m = computed(() => props.topic('motion'))
const joints = computed(() => m.value.joints || [])
const names = computed(() => m.value.joint_names || [])

// 两列排布：16 关节 → 8 行
const rows = computed(() => {
  const out = []
  for (let i = 0; i < joints.value.length; i += 2) {
    out.push([
      { name: names.value[i] || ('joint_' + i), value: joints.value[i] },
      { name: names.value[i + 1] || ('joint_' + (i + 1)), value: joints.value[i + 1] }
    ])
  }
  return out
})

function fmt (v) {
  return (v === undefined || v === null) ? '—' : Number(v).toFixed(3)
}
</script>

<style scoped>
table { font-size: var(--fs-13); }
td.num { font-variant-numeric: tabular-nums; color: var(--text-strong); }
</style>
