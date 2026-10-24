<template>
  <!-- 选项按钮组（下拉框的替代形态，2026-10-20 加）
       --------------------------------------------------------------
       为什么替掉 <select>：
         · 下拉框**不显示当前值** —— 不展开就不知道现在选的是哪一项，监控页上
           一眼扫不出"当前步态 / 当前方向 / 当前通道"，每次都要多点一次；
         · 这几个选项都只有 2~6 档且**互斥**，摆成按钮组可一次看全；
         · 高亮项 = **当前选择的档位**，配合旁边"当前生效"的回读值，
           选择值与车侧真实值不再混淆（下发后 1~2s 内可能不一致）；
         · 每档可单独给 tooltip 讲清后果，比 option 里的长文本更好读。

       与 DeviceToggle.vue 的关系：DeviceToggle 只管「开 / 关」两档，
       本组件管**任意多档**，两者共用同一套视觉语言（段组 + 高亮 + 加载态）。
       排版与旁边的 `.field` 表单项一致（标签在上、控件在下）。 -->
  <span class="seg" :class="{ unknown: !known, inline: !label }">
    <span v-if="label" class="seg-label">{{ label }}</span>
    <span class="seg-line">
      <span class="seg-group" role="group" :aria-label="`${groupName} 选择`">
        <button
          v-for="o in options"
          :key="String(o.value)"
          type="button"
          class="seg-btn"
          :class="{ active: known && o.value === current }"
          :disabled="disabled || busy || !known"
          :aria-pressed="known && o.value === current"
          :title="tipOf(o)"
          @click="pick(o.value)"
        >{{ o.label }}</button>
      </span>
      <!-- 切换中：给可见的加载反馈，避免"点了没反应"时重复点击 -->
      <span v-if="busy" class="spinner" :title="`${groupName} 切换中…`" />
      <span v-if="!known" class="seg-unknown" title="尚未收到车侧上报，无法确定当前值">待上报</span>
    </span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** 分组名，如「步态」「方向」；**留空则行内显示**（只有按钮组，用在标题行右侧等紧凑位置） */
  label: { type: String, default: '' },
  /** 无可见标签时的无障碍名（读屏用），如「摇杆水平轴模式」 */
  ariaLabel: { type: String, default: '' },
  /** 选项：{ value, label, tip } —— value 与当前值**严格相等**才算选中 */
  options: { type: Array, required: true },
  /** 当前值；null / undefined 表示"尚未收到上报"，所有档不高亮且禁用 */
  value: { type: [Number, String], default: null },
  /** 控制未开启 / 操作进行中时禁用 */
  disabled: { type: Boolean, default: false },
  /** 有指令在途（本组或其他），转圈 + 禁用 */
  busy: { type: Boolean, default: false }
})

const emit = defineEmits(['set'])

const known = computed(() => props.value !== null && props.value !== undefined)
const current = computed(() => props.value)
/** 无障碍名 / 加载文案用：无可见标签时退回 ariaLabel */
const groupName = computed(() => props.label || props.ariaLabel || '选项')

/** 悬停说明：优先用选项自带 tip，否则按"是否当前值"给默认文案 */
function tipOf (o) {
  if (o.tip) return o.tip
  if (!known.value) return '尚未收到车侧上报，暂不可操作'
  if (o.value === current.value) return `当前选择：${o.label}（已是该值，点击不会重复下发）`
  return `切换到「${o.label}」（会立即下发给车侧）`
}

function pick (v) {
  if (!known.value) return
  if (v === current.value) return          // 已是当前值：不发冗余指令
  emit('set', v)
}
</script>

<style scoped>
.seg {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  font-size: var(--fs-12);
}
.seg.unknown .seg-label { opacity: 0.6; }

/* 行内形态（无可见标签）：按钮组直接跟着标题走，不额外占一行 */
.seg.inline {
  flex-direction: row;
  align-items: center;
}

.seg-label { color: var(--muted); }

/* 控件行：段组 + 加载转圈 / 待上报标记 */
.seg-line {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2);
}

/* 段组：1px 缝隙由容器底色透出，比每条按钮各画边框更像"一个控件" */
.seg-group {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 1px;
  padding: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}

.seg-btn {
  min-height: 24px;
  padding: var(--sp-1) var(--sp-3);
  font-family: inherit;
  font-size: var(--fs-12);
  color: var(--muted);
  background: var(--panel);
  border: 0;
  border-radius: calc(var(--r-sm) - 2px);
}

.seg-btn:hover:not(:disabled):not(.active) {
  color: var(--text);
  background: var(--panel-3);
}

/* 当前值：实心高亮，扫一眼就知道选的是哪个 */
.seg-btn.active {
  color: #fff;
  background: var(--accent-strong);
  font-weight: 600;
}

/* 禁用态：仍要能看出"当前是哪一档"，所以只降透明度、不改配色 */
.seg-btn:disabled { opacity: 0.45; }
.seg-btn.active:disabled { opacity: 0.85; }

.seg-unknown {
  padding: 0 var(--sp-2);
  font-size: var(--fs-11);
  color: var(--warn);
  border: 1px dashed var(--warn-line);
  border-radius: var(--r-pill);
}
</style>
