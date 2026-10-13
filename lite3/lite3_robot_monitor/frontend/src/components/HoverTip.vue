<script setup>
/**
 * HoverTip.vue
 * 通用悬停提示。用于在不干扰原有内容的前提下补充说明信息。
 *
 * 设计要点：
 * 1. 内容用 <Teleport to="body"> 挂到 body：不受父级 overflow / z-index 影响，也不会撑开原布局；
 * 2. tooltip 本身 pointer-events: none —— 绝不拦截下方元素的鼠标事件（不影响原交互）；
 * 3. 出现/消失无延迟（仅 100ms 透明度过渡），离开即隐藏；
 * 4. 自动做视口边缘翻转，超出右/下边界时改为贴边或翻到上方，避免被裁切。
 */
import { ref, nextTick, onBeforeUnmount } from 'vue'

const props = defineProps({
  /** 与触发元素的间距（px） */
  gap: { type: Number, default: 8 },
  /** 提示最大宽度（px） */
  maxWidth: { type: Number, default: 320 }
})

const wrapEl = ref(null)
const tipEl = ref(null)
const visible = ref(false)
const placed = ref(false)
const pos = ref({ top: '0px', left: '0px' })

async function show() {
  visible.value = true
  placed.value = false
  await nextTick()
  place()
  placed.value = true
}

function hide() {
  visible.value = false
  placed.value = false
}

function place() {
  const w = wrapEl.value
  const t = tipEl.value
  if (!w || !t) return

  const wr = w.getBoundingClientRect()
  const tr = t.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const margin = 8

  // 水平：默认与触发器左对齐，右侧越界则贴右边界
  let left = wr.left
  if (left + tr.width > vw - margin) left = vw - tr.width - margin
  if (left < margin) left = margin

  // 垂直：优先放下方，下方放不下则翻到上方，都放不下则贴底
  let top = wr.bottom + props.gap
  if (top + tr.height > vh - margin) {
    const above = wr.top - tr.height - props.gap
    top = above >= margin ? above : Math.max(margin, vh - tr.height - margin)
  }

  pos.value = { top: `${Math.round(top)}px`, left: `${Math.round(left)}px` }
}

function onViewportChange() {
  if (visible.value) place()
}

window.addEventListener('scroll', onViewportChange, true)
window.addEventListener('resize', onViewportChange)

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onViewportChange, true)
  window.removeEventListener('resize', onViewportChange)
})
</script>

<template>
  <span
    ref="wrapEl"
    class="tip-wrap"
    @mouseenter="show"
    @mouseleave="hide"
    @focusin="show"
    @focusout="hide"
  >
    <slot />
    <Teleport to="body">
      <div
        v-if="visible"
        ref="tipEl"
        class="hover-tip"
        :class="{ placed }"
        :style="{ top: pos.top, left: pos.left, maxWidth: `${maxWidth}px` }"
        role="tooltip"
      >
        <slot name="tip" />
      </div>
    </Teleport>
  </span>
</template>

<style scoped>
/* 包裹层不参与布局计算，避免影响原有内容排布 */
.tip-wrap {
  display: inline-flex;
  align-items: center;
}
</style>

<style>
/* Teleport 到 body，不能用 scoped */
.hover-tip {
  position: fixed;
  z-index: 2000;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #e2e8f0;
  background: #1e293b;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.28);
  /* 关键：不拦截鼠标事件，避免遮挡下方内容的交互 */
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.1s ease;
}

.hover-tip.placed {
  opacity: 1;
}
</style>
