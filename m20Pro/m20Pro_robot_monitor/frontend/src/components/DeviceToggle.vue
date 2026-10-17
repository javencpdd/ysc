<template>
  <!-- 设备开关：**状态 + 动作分离**（2026-10-17 修）。
       此前按钮文字写的是"点了会做什么"（当前开着就显示「关闭」），界面上却没有
       任何当前状态的指示 → 用户看到一排「关闭」会以为"只能关不能开"。
       现在把「开 / 关」两个选项都摆出来，高亮的是**当前状态**，点另一个即切换。
       （与 GPS 页的卫星系统模式选择器同一范式，全站一致。） -->
  <span class="dt" :class="{ unknown: !known }">
    <span class="dt-label">{{ label }}</span>
    <span class="dt-seg">
      <button
        type="button"
        class="dt-btn"
        :class="{ active: known && on }"
        :disabled="disabled || busy || !known"
        :title="tip(true)"
        @click="set(true)"
      >开</button>
      <button
        type="button"
        class="dt-btn"
        :class="{ active: known && !on }"
        :disabled="disabled || busy || !known"
        :title="tip(false)"
        @click="set(false)"
      >关</button>
    </span>
    <span v-if="hint" class="dt-hint">{{ hint }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** 设备名，如「主机电源指示灯」 */
  label: { type: String, required: true },
  /**
   * 当前值。**只要非 0 即视为"开"** —— 雷达上报 2（运行中）也是开，
   * 写 `=== 1` 会把运行中的雷达误判成已关闭（见后端 DEVICE_SWITCH_SPEC 注释）。
   * `null` = 尚未收到上报（两个选项都不高亮且禁用，绝不猜）。
   */
  value: { type: [Number, String], default: null },
  /** 控制通道未开启 / 正在下发时禁用 */
  disabled: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  /** 附加展示（如风扇转速 100） */
  hint: { type: [String, Number], default: '' }
})

const emit = defineEmits(['set'])

const known = computed(() => props.value !== null && props.value !== undefined)
const on = computed(() => (known.value ? Number(props.value) !== 0 : false))

function tip (wantOn) {
  if (!known.value) return '尚未收到车侧上报'
  if (props.disabled) return '需先在「运动控制」页开启控制（L1）'
  if (wantOn === on.value) return `当前：${on.value ? '开' : '关'}`
  return wantOn ? `开启${props.label}` : `关闭${props.label}`
}

function set (wantOn) {
  if (!known.value) return
  if (wantOn === on.value) return          // 已是该状态：不发冗余指令
  emit('set', wantOn ? 1 : 0)
}
</script>

<style scoped>
.dt {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  font-size: 12px;
}
.dt.unknown .dt-label { opacity: 0.55; }
.dt-label { color: var(--muted, #888); }
.dt-seg {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
}
.dt-btn {
  padding: 2px 9px;
  font-family: inherit;
  font-size: 12px;
  color: var(--muted, #888);
  background: transparent;
  border: 0;
  border-right: 1px solid var(--line);
}
.dt-btn:last-child { border-right: 0; }
.dt-btn.active {
  color: #fff;
  background: var(--accent, #2f6fed);
  font-weight: 600;
}
.dt-btn:disabled { opacity: 0.45; }
.dt-btn.active:disabled { opacity: 0.75; }   /* 当前态保持可辨认 */
.dt-hint { color: var(--muted, #888); font-variant-numeric: tabular-nums; }
</style>
