<script setup>
/**
 * JointPanel.vue
 * 12 个关节的角度（rad / deg）与角速度展示。
 */
import { computed } from 'vue'
import RosInfoTip from './RosInfoTip.vue'

const props = defineProps({
  /** 0x0902 关节角度对象 */
  angle: { type: Object, default: null },
  /** 0x0903 关节角速度对象 */
  velocity: { type: Object, default: null },
  /** 当前生效数据源：ros / sniff / bind（供 ROS 提示判定） */
  dataSource: { type: String, default: '' },
  /** 数据是否由 ros_bridge 转发 */
  fromRos: { type: Boolean, default: false }
})

/** 关节名称，后端未提供时退化为 joint_N */
const names = computed(() => props.angle?.joint_names || props.velocity?.joint_names || [])

/** 角度数据（rad） */
const angles = computed(() => props.angle?.joint || [])
/** 角速度数据（rad/s） */
const velocities = computed(() => props.velocity?.velocity || [])

/** 弧度转角度 */
const toDeg = (rad) => (rad * 180) / Math.PI

/** 合并成行数据，便于模板统一遍历 */
const rows = computed(() => {
  const count = Math.max(angles.value.length, velocities.value.length, names.value.length, 12)
  return Array.from({ length: count }, (_, i) => ({
    index: i,
    name: names.value[i] || `joint_${i}`,
    angle: typeof angles.value[i] === 'number' ? angles.value[i] : null,
    velocity: typeof velocities.value[i] === 'number' ? velocities.value[i] : null
  }))
})

/** 关节行程经验区间 [-0.9, 0.9] rad，用于绘制归一化进度条 */
const ANGLE_RANGE = 0.9

function percent(rad) {
  if (rad === null) return 50
  const p = ((rad + ANGLE_RANGE) / (2 * ANGLE_RANGE)) * 100
  return Math.max(2, Math.min(98, p))
}
</script>

<template>
  <section class="card">
    <div class="card-title">
      <span>
        Joint / 12 DOF
        <RosInfoTip area="joint" :source="dataSource" :from-ros="fromRos" />
      </span>
      <span class="sub">角度 {{ angle?.unit || 'rad' }} · 角速度 {{ velocity?.unit || 'rad/s' }}</span>
    </div>

    <div v-if="!rows.length" class="empty">等待关节数据 (0x0902 / 0x0903) ...</div>

    <div v-else class="joint-grid">
      <div v-for="row in rows" :key="row.index" class="joint">
        <div class="joint-head">
          <span class="joint-name mono">{{ row.name }}</span>
          <span class="joint-val mono">
            {{ row.angle === null ? '--' : row.angle.toFixed(4) }}
            <em>rad</em>
          </span>
        </div>
        <div class="bar">
          <div class="bar-fill" :style="{ width: percent(row.angle) + '%' }" />
        </div>
        <div class="joint-foot mono">
          <span>{{ row.angle === null ? '--' : toDeg(row.angle).toFixed(2) }}°</span>
          <span class="vel">{{ row.velocity === null ? '--' : row.velocity.toFixed(4) }} rad/s</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.joint-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.joint {
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid #e6ecf3;
  border-radius: 10px;
}

.joint-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.joint-name {
  font-size: 12px;
  color: #475569;
  font-weight: 600;
}

.joint-val {
  font-size: 13px;
  color: var(--text);
}

.joint-val em {
  font-style: normal;
  font-size: 11px;
  color: #94a3b8;
}

.bar {
  margin: 8px 0 6px;
  height: 6px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #60a5fa, #2563eb);
  border-radius: 999px;
  transition: width 0.15s linear;
}

.joint-foot {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-sub);
}

.vel {
  color: #64748b;
}

.empty {
  padding: 24px 0;
  text-align: center;
  color: #94a3b8;
}
</style>
