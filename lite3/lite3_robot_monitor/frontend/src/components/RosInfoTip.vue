<script setup>
/**
 * RosInfoTip.vue
 * ROS 数据来源说明的悬停标记。
 *
 * 仅在数据确实来自 ROS 时展示话题/类型/字段结构；否则给出明确的兜底文案，
 * 避免用户在 sniff 模式下以为看到的是 ROS 话题信息。
 */
import { computed } from 'vue'
import HoverTip from './HoverTip.vue'
import { getRosMeta } from '../utils/rosMeta.js'

const props = defineProps({
  /** 数据区域：imu | odom | joint（对应 rosMeta.js 中登记的 area） */
  area: { type: String, required: true },
  /** 当前生效数据源模式：ros / sniff / bind / none */
  source: { type: String, default: '' },
  /** 数据是否确实由 ros_bridge 转发（robot_state.source.ip === 'ros_bridge'） */
  fromRos: { type: Boolean, default: false }
})

const meta = computed(() => getRosMeta(props.area))

/** 是否处于 ROS 数据源：模式为 ros，或数据里带 ros_bridge 标记 */
const isRos = computed(() => props.source === 'ros' || props.fromRos)

const SOURCE_TEXT = {
  ros: 'ROS 话题订阅',
  sniff: 'sniff 旁路抓包',
  bind: 'UDP 端口绑定',
  none: '无数据源'
}
</script>

<template>
  <HoverTip :max-width="360">
    <span
      class="ros-mark"
      :class="{ active: isRos }"
      tabindex="0"
      :aria-label="`${meta ? meta.label : '数据来源'}：ROS 话题与字段说明`"
    >i</span>

    <template #tip>
      <!-- 正常：ROS 数据源且已登记元数据 -->
      <div v-if="meta && isRos" class="ros-tip">
        <div class="tip-title">{{ meta.label }}</div>

        <div class="tip-sec">
          <span class="tip-k">话题</span>
          <span
            v-for="t in meta.topics"
            :key="t.name"
            class="mono tip-topic"
          >{{ t.name }}</span>
        </div>

        <div class="tip-sec">
          <span class="tip-k">消息类型</span>
          <span
            v-for="t in meta.topics"
            :key="`${t.name}-type`"
            class="mono tip-type"
          >{{ t.type }}</span>
        </div>

        <div v-if="meta.mapping?.length" class="tip-block">
          <div class="tip-sub">字段映射</div>
          <div v-for="(m, i) in meta.mapping" :key="i" class="tip-row">
            <span class="mono tip-from">{{ m.from }}</span>
            <span class="tip-arrow">→</span>
            <span class="mono tip-to">{{ m.to }}</span>
            <span v-if="m.note" class="tip-note">{{ m.note }}</span>
          </div>
        </div>

        <div v-if="meta.fields?.length" class="tip-block">
          <div class="tip-sub">字段结构</div>
          <table class="tip-table">
            <tbody>
              <tr v-for="f in meta.fields" :key="f.name">
                <td class="mono">{{ f.name }}</td>
                <td class="mono dim">{{ f.type }}</td>
                <td class="dim">{{ f.unit || '—' }}</td>
                <td>{{ f.desc }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="meta.example" class="tip-block">
          <div class="tip-sub">示例数据</div>
          <pre class="mono tip-example">{{ meta.example }}</pre>
        </div>

        <div v-if="meta.caveats?.length" class="tip-caveat">
          <div v-for="(c, i) in meta.caveats" :key="i">· {{ c }}</div>
        </div>
      </div>

      <!-- 兜底 1：不是 ROS 数据源 -->
      <div v-else-if="!isRos" class="ros-tip">
        <div class="tip-title">暂无 ROS 话题信息</div>
        <div class="tip-fallback">
          当前数据源为 <b>{{ SOURCE_TEXT[source] || source || '未知' }}</b>，
          该区域的数据<b>不来自 ROS 话题</b>，因此没有关联的话题名与消息类型。
        </div>
        <div class="tip-fallback dim">
          如需查看 ROS 话题与字段结构，请在操作台「监听模式」切换到
          <b>ROS 话题订阅</b>（ros），并确保 lite3-ros-bridge 服务在运行。
        </div>
      </div>

      <!-- 兜底 2：是 ROS 但该区域未登记元数据 -->
      <div v-else class="ros-tip">
        <div class="tip-title">未登记的 ROS 数据区域</div>
        <div class="tip-fallback">
          区域 <b class="mono">{{ area }}</b> 尚未登记 ROS 元数据，无法给出话题与字段说明。
        </div>
        <div class="tip-fallback dim">
          请在 <span class="mono">frontend/src/utils/rosMeta.js</span> 的
          <span class="mono">ROS_META</span> 中补充该 area 的描述符。
        </div>
      </div>
    </template>
  </HoverTip>
</template>

<style scoped>
.ros-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  margin-left: 5px;
  font-size: 9.5px;
  font-style: italic;
  font-weight: 700;
  color: #94a3b8;
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  border-radius: 50%;
  cursor: help;
  vertical-align: middle;
}

.ros-mark.active {
  color: #fff;
  background: #7c3aed;
  border-color: #7c3aed;
}

.ros-mark:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 1px;
}
</style>

<style>
/* Teleport 出去的提示内容，不可用 scoped */
.ros-tip { font-size: 12px; }

.tip-title {
  margin-bottom: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: #f8fafc;
}

.tip-sec {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 4px;
}

.tip-k {
  flex: none;
  width: 58px;
  color: #94a3b8;
}

.tip-topic {
  padding: 1px 6px;
  color: #c4b5fd;
  background: rgba(124, 58, 237, 0.18);
  border-radius: 4px;
}

.tip-type {
  padding: 1px 6px;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.18);
  border-radius: 4px;
}

.tip-block { margin-top: 8px; }

.tip-sub {
  margin-bottom: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #cbd5e1;
}

.tip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: baseline;
  margin-bottom: 3px;
}

.tip-from { color: #fcd34d; }
.tip-arrow { color: #64748b; }
.tip-to { color: #86efac; }
.tip-note { color: #94a3b8; font-size: 11px; }

.tip-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.tip-table td {
  padding: 2px 6px 2px 0;
  color: #e2e8f0;
  vertical-align: top;
}

.tip-table .dim { color: #94a3b8; }

.tip-example {
  max-height: 150px;
  margin: 0;
  padding: 6px 8px;
  overflow: auto;
  font-size: 10.5px;
  line-height: 1.5;
  color: #a5b4fc;
  background: rgba(15, 23, 42, 0.6);
  border-radius: 5px;
  white-space: pre;
}

.tip-caveat {
  margin-top: 8px;
  padding-top: 6px;
  font-size: 11px;
  color: #fcd34d;
  border-top: 1px dashed rgba(148, 163, 184, 0.35);
}

.tip-fallback { margin-bottom: 4px; color: #e2e8f0; }
.tip-fallback b { color: #fcd34d; }
.tip-fallback.dim { color: #94a3b8; font-size: 11px; }
</style>
