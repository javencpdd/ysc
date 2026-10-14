<template>
  <header style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px">
    <h2 style="margin: 0">M20 Pro 机器人控制台</h2>
    <div style="color: var(--muted); font-size: 12px">
      数据源 {{ svc.data_source || '—' }} · 推送 {{ svc.push_hz || 10 }}Hz ·
      WS 客户端 {{ svc.ws_clients ?? 0 }} ·
      <span :style="{ color: connected ? 'var(--ok)' : 'var(--danger)' }">
        {{ connected ? '链路在线' : '链路断开' }}
      </span>
    </div>
  </header>

  <!-- 降级：数据停更必须显式暴露，绝不把旧数据当新数据展示（PLAN §6.2） -->
  <div v-if="!connected" class="banner">
    ⚠ 数据已停更 {{ sinceSeconds.toFixed(1) }}s —— 以下数值为最后收到的快照，可能已过期
  </div>
  <div v-else-if="staleTopics.length" class="banner" style="background: var(--warn)">
    部分数据停更：{{ staleTopics.join('、') }}（对应面板已置灰）
  </div>

  <RobotStatus :topic="topic" :is-stale="isStale" />
  <JointPanel :topic="topic" :is-stale="isStale" />
  <MotionPanel
    :control="control"
    :send-command="sendCommand"
    :send-axis="sendAxis"
    :stop-axis="stopAxis"
    :estop="estop"
    :clear-estop="clearEstop"
    :enable-control="enableControl"
    :disable-control="disableControl"
    :renew-lease="renewLease"
  />
  <VideoPanel />
</template>

<script setup>
import { computed } from 'vue'
import RobotStatus from './components/RobotStatus.vue'
import JointPanel from './components/JointPanel.vue'
import MotionPanel from './components/MotionPanel.vue'
import VideoPanel from './components/VideoPanel.vue'
import { useRobotState } from './composables/useRobotState.js'

const s = useRobotState()
const {
  snapshot, topics, connected, staleTopics, sinceSeconds, control,
  topic, isStale, sendCommand, sendAxis, stopAxis, estop, clearEstop,
  enableControl, disableControl, renewLease
} = s

const svc = computed(() => (snapshot.value && snapshot.value.service) || {})
</script>
