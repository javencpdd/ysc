<template>
  <div class="panel" :class="{ stale: isStale('basic') }">
    <h3>基础状态 <small>（1002/6 · 2Hz）</small></h3>
    <div class="grid">
      <div class="kv"><span>运动状态</span><span>{{ b.motion_state_label || '—' }}</span></div>
      <div class="kv"><span>步态</span><span>{{ b.gait_label || '—' }}</span></div>
      <div class="kv"><span>使用模式</span><span>{{ b.control_usage_mode_label || '—' }}</span></div>
      <div class="kv"><span>充电状态</span><span>{{ b.charge_label || '—' }}</span></div>
      <div class="kv"><span>硬急停 HES</span><span>{{ b.hes === 1 ? '已触发' : '未触发' }}</span></div>
      <div class="kv"><span>休眠</span><span>{{ b.sleep_label || '—' }}</span></div>
      <div class="kv"><span>辅助避障</span><span>{{ b.ooa ?? '—' }}</span></div>
      <div class="kv"><span>电源模式</span><span>{{ b.power_management === 1 ? '单电池' : '常规' }}</span></div>
      <div class="kv"><span>机型</span><span>{{ b.version || '—' }}</span></div>
    </div>
  </div>

  <div class="panel" :class="{ stale: isStale('device') }">
    <h3>设备状态 <small>（1002/5 · 2Hz · BatteryList）</small></h3>
    <div v-if="d.battery_count" class="grid">
      <div class="kv"><span>电量</span><span>{{ d.level }} %</span></div>
      <div class="kv"><span>电压</span><span>{{ d.voltage }} V</span></div>
      <div class="kv"><span>温度</span><span>{{ d.temperature }} ℃</span></div>
      <div class="kv"><span>充电中</span><span>{{ d.charging ? '是' : '否' }}</span></div>
      <div class="kv"><span>电池块数</span><span>{{ d.battery_count }}</span></div>
    </div>
    <div v-else style="color: var(--muted)">暂无电池数据</div>
  </div>

  <div class="panel" :class="{ stale: isStale('fault') }">
    <h3>异常状态 <small>（1002/3）</small></h3>
    <div v-if="f.error_count" >
      <table>
        <thead><tr><th>错误码</th><th>部件</th></tr></thead>
        <tbody>
          <tr v-for="(e, i) in f.errors" :key="i">
            <td>{{ e.code }}</td><td>{{ e.component }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else style="color: var(--ok)">无异常</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  topic: { type: Function, required: true },
  isStale: { type: Function, required: true }
})

const b = computed(() => props.topic('basic'))
const d = computed(() => props.topic('device'))
const f = computed(() => props.topic('fault'))
</script>
