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

    <!-- 逐块渲染：真机两块电池。旧版只显示 batteries[0]，而单电池模式下
         左电池全 0（=未安装），于是面板显示"电量 0 %"——看起来像"没有电量信息"
         （2026-10-16 修：逐块显示 + 明确标注未安装 + 低电量着色） -->
    <div v-if="batteries.length" class="bats">
      <div v-for="(bat, i) in batteries" :key="i" class="bat">
        <div class="bat-top">
          <span class="bat-name">
            电池 {{ i + 1 }}<small>{{ i === 0 ? '（左）' : i === 1 ? '（右）' : '' }}</small>
          </span>
          <span class="bat-pct" :class="levelClass(bat)">
            {{ installed(bat) ? Math.round(Number(bat.level)) + '%' : '未安装 / 无数据' }}
          </span>
        </div>
        <div class="bar">
          <div class="bar-fill" :class="levelClass(bat)" :style="{ width: barWidth(bat) }"></div>
        </div>
        <div class="bat-meta">
          <span>{{ fmt(bat.voltage) }} V</span>
          <span>{{ fmt(bat.temperature) }} ℃</span>
          <span>{{ bat.charging ? '充电中' : (installed(bat) ? '未充电' : '—') }}</span>
        </div>
      </div>
      <div class="bat-note">
        电源模式：<b>{{ powerModeLabel }}</b>
        <span v-if="missingCount">
          （{{ missingCount }} 块未安装/无数据 —— 单电池模式下属正常，不是故障）
        </span>
      </div>
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
const f = computed(() => props.topic('fault'))

// ---- 电池：逐块展示（真机 2 块）----
const batteries = computed(() => {
  const list = props.topic('device')?.batteries
  return Array.isArray(list) ? list : []
})

/**
 * 电池是否"在位"。判定：level 缺失 → 不在位；level 与 voltage **同时为 0** → 不在位。
 * 依据（2026-10-16 真机）：power_management=1（单电池模式）时左电池上报
 * level=0 / voltage=0 / 温度=0，而右电池 64% / 76V / 29.4℃——全 0 即未安装。
 */
function installed (bat) {
  if (!bat || bat.level == null) return false
  return !(Number(bat.level) === 0 && Number(bat.voltage) === 0)
}

function levelClass (bat) {
  if (!installed(bat)) return 'na'
  const l = Number(bat.level)
  if (l < 20) return 'low'      // 该充电了
  if (l < 50) return 'mid'
  return 'ok'
}

const barWidth = (bat) =>
  installed(bat) ? `${Math.max(0, Math.min(100, Number(bat.level)))}%` : '0%'

const fmt = (v) =>
  v == null || Number.isNaN(Number(v))
    ? '—'
    : String(Math.round(Number(v) * 10) / 10)

const missingCount = computed(() => batteries.value.filter((x) => !installed(x)).length)
const powerModeLabel = computed(() =>
  props.topic('basic')?.power_management === 1 ? '单电池' : '常规（双电池）')
</script>

<style scoped>
.bats {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bat {
  border: 1px solid rgba(128, 128, 128, 0.35);
  border-radius: 6px;
  padding: 8px 10px;
}
.bat-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.bat-name {
  font-size: 13px;
}
.bat-name small {
  color: var(--muted, #888);
}
.bat-pct {
  font-size: 16px;
  font-weight: 600;
}
.bar {
  height: 8px;
  background: rgba(128, 128, 128, 0.25);
  border-radius: 4px;
  overflow: hidden;
  margin: 6px 0 4px;
}
.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}
.bar-fill.ok { background: #2e9e5b; }
.bar-fill.mid { background: #c8901e; }
.bar-fill.low { background: #d0453b; }
.bar-fill.na { background: rgba(128, 128, 128, 0.4); }
.bat-pct.ok { color: var(--ok, #2e9e5b); }
.bat-pct.mid { color: var(--warn, #c8901e); }
.bat-pct.low { color: var(--danger, #d0453b); }
.bat-pct.na { color: var(--muted, #888); font-size: 13px; font-weight: 400; }
.bat-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--muted, #999);
}
.bat-note {
  font-size: 12px;
  color: var(--muted, #888);
  margin-top: 2px;
}
</style>
