<script setup>
/**
 * RobotStatus.vue
 * 顶部状态卡片：基本状态、步态、AI 步态、电池电量、链路连接情况。
 */
import { computed } from 'vue'

const props = defineProps({
  /** 0x0901 机器人综合状态对象 */
  state: { type: Object, default: null },
  /** 服务运行状态对象（GET /api/status） */
  status: { type: Object, default: null },
  /** WebSocket 连接状态字符串 */
  wsStatus: { type: String, default: 'closed' }
})

/** 电池电量（0-100） */
const battery = computed(() => {
  const v = props.state?.battery
  if (typeof v !== 'number' || Number.isNaN(v)) return 0
  return Math.max(0, Math.min(100, v))
})

/** 电量条配色：高于 40% 正常，20-40% 警告，低于 20% 危险 */
const batteryLevel = computed(() => {
  if (battery.value >= 40) return 'ok'
  if (battery.value >= 20) return 'warn'
  return 'danger'
})

/** 机器人链路在线与否 */
const connected = computed(() => Boolean(props.status?.connected))

/** WebSocket 侧的显示文案 */
const wsText = computed(() => {
  switch (props.wsStatus) {
    case 'open':
      return 'WebSocket 已连接'
    case 'connecting':
      return 'WebSocket 连接中'
    default:
      return 'WebSocket 未连接'
  }
})

/** 关节是否已回零 */
const zeroText = computed(() =>
  props.state?.zero_position_flag ? '已回零' : '未回零'
)
</script>

<template>
  <section class="card status-card">
    <div class="card-title">
      <span>Robot Status</span>
      <span class="sub">{{ state?.code || '0x0901' }}</span>
    </div>

    <div class="grid">
      <!-- 连接状态 -->
      <div class="cell">
        <span class="label">连接状态</span>
        <div class="badge-row">
          <span class="dot" :class="connected ? 'ok' : 'off'" />
          <strong :class="connected ? 'text-ok' : 'text-off'">
            {{ connected ? 'Connected' : 'Disconnected' }}
          </strong>
        </div>
        <span class="hint">{{ wsText }}</span>
      </div>

      <!-- 基本状态 -->
      <div class="cell">
        <span class="label">当前状态</span>
        <strong class="big">{{ state?.basic_state || '--' }}</strong>
        <span class="hint mono">code {{ state?.basic_state_code ?? '-' }}</span>
      </div>

      <!-- 步态 -->
      <div class="cell">
        <span class="label">当前步态</span>
        <strong class="big">{{ state?.gait_state || '--' }}</strong>
        <span class="hint">AI 步态：{{ state?.policy_state || '--' }}</span>
      </div>

      <!-- 电池 -->
      <div class="cell">
        <span class="label">电池电量</span>
        <div class="battery-head">
          <strong class="big mono">{{ battery.toFixed(1) }}%</strong>
          <span class="hint" v-if="state?.is_charging">充电中</span>
        </div>
        <div class="battery-bar">
          <div class="fill" :class="batteryLevel" :style="{ width: battery + '%' }" />
        </div>
      </div>
    </div>

    <!-- 次级指标 -->
    <div class="chips">
      <span class="chip">动作：{{ state?.motion_state || '--' }}</span>
      <span class="chip">回零：{{ zeroText }}</span>
      <span class="chip" :class="{ alert: state?.is_robot_need_move }">
        外力平衡：{{ state?.is_robot_need_move ? '需调整' : '稳定' }}
      </span>
      <span class="chip">语音控制：{{ state?.is_voice_ctrl_enable ? '开启' : '关闭' }}</span>
      <span class="chip" :class="{ alert: state?.error_state }">错误码：{{ state?.error_state ?? '-' }}</span>
      <span class="chip">超声波 前 {{ (state?.ultrasound?.forward ?? 0).toFixed(2) }} m / 后
        {{ (state?.ultrasound?.backward ?? 0).toFixed(2) }} m</span>
    </div>
  </section>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}

.cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: var(--accent-soft);
  border: 1px solid #dbe6ff;
  border-radius: 10px;
}

.label {
  font-size: 12px;
  color: var(--text-sub);
}

.big {
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
}

.hint {
  font-size: 12px;
  color: #94a3b8;
}

.badge-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #cbd5e1;
}

.dot.ok {
  background: var(--ok);
  box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.15);
  animation: pulse 1.6s infinite;
}

.dot.off {
  background: var(--danger);
  box-shadow: 0 0 0 4px rgba(220, 38, 38, 0.12);
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.45; }
  100% { opacity: 1; }
}

.text-ok { color: var(--ok); }
.text-off { color: var(--danger); }

.battery-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.battery-bar {
  margin-top: 6px;
  height: 8px;
  width: 100%;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
}

.battery-bar .fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}

.fill.ok { background: var(--ok); }
.fill.warn { background: var(--warn); }
.fill.danger { background: var(--danger); }

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.chip {
  padding: 4px 10px;
  font-size: 12px;
  color: #334155;
  background: var(--chip-bg);
  border: 1px solid #e2e8f0;
  border-radius: 999px;
}

.chip.alert {
  color: #b45309;
  background: #fffbeb;
  border-color: #fde68a;
}
</style>
