<template>
  <!-- 可折叠分区卡片（2026-10-20 加）
       --------------------------------------------------------------
       动机：运动控制页经过多轮迭代已经很长（控制权 / 车侧反馈 / 摇杆 / 定时移动
       四块），一屏放不下；但每块的"标题 + 当前状态"必须**始终可见** —— 否则折叠后
       用户既不知道里面是什么，也不知道当前处于什么状态（例如定时移动执行中）。

       所以折叠的只是正文，头部常驻：标题 + 提示 + 右上角徽标插槽（badge）。
       折叠状态按 storeKey 存 localStorage，刷新 / 换终端登录后保持用户的展开偏好。

       与 .msec 的关系：外观与普通分区一致（同 class），只多一个可点头部，
       所以两种写法可以混用而不破坏排版。 -->
  <section class="msec collapsible" :class="{ open }">
    <button
      class="msec-head collapsible-head"
      type="button"
      :aria-expanded="open ? 'true' : 'false'"
      :title="open ? '点击折叠本分区' : `点击展开「${title}」`"
      @click="toggle"
    >
      <span class="collapsible-arrow" :class="{ open }" aria-hidden="true" />
      <span class="block-title">{{ title }}</span>
      <span v-if="hint" class="hint">{{ hint }}</span>
      <span class="spacer" />
      <!-- 徽标：放"折叠时也要看得见"的状态，如「执行中 · 剩余 3.2s」 -->
      <slot name="badge" />
    </button>

    <!-- 正文：用 grid-template-rows 0fr→1fr 做高度动画（内容多高就动多高，
         不用写死 max-height）；collapsible-inner 负责裁切 + 折叠后移出 Tab 焦点链 -->
    <div class="collapsible-body" :class="{ open }">
      <div class="collapsible-inner">
        <slot />
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  /** 标题右侧的浅色说明，讲清"这块是干什么的" */
  hint: { type: String, default: '' },
  /** 无存储键时的默认展开状态 */
  defaultOpen: { type: Boolean, default: true },
  /** localStorage 键名（如 'joystick'）：记住用户的展开偏好 */
  storeKey: { type: String, default: '' }
})
const emit = defineEmits(['update:open'])

const STORE_PREFIX = 'm20monitor:collapse:'

/** 读取上次的展开状态；localStorage 不可用（隐私模式等）时退回默认值 */
function readStored () {
  if (!props.storeKey) return props.defaultOpen
  try {
    const v = localStorage.getItem(STORE_PREFIX + props.storeKey)
    return v === null ? props.defaultOpen : v === '1'
  } catch (e) {
    return props.defaultOpen
  }
}

const open = ref(readStored())

watch(open, (v) => {
  emit('update:open', v)
  if (!props.storeKey) return
  try { localStorage.setItem(STORE_PREFIX + props.storeKey, v ? '1' : '0') } catch (e) { /* 忽略写入失败 */ }
})

function toggle () { open.value = !open.value }
</script>

<style scoped>
.collapsible-head {
  width: 100%;
  font: inherit;
  text-align: left;
  cursor: pointer;
  background: none;
  border: 0;
}
.collapsible-head:hover .block-title { color: var(--text); }

/* 折叠箭头：CSS 三角，收起时朝右、展开时朝下（旋转 90°） */
.collapsible-arrow {
  flex: 0 0 auto;
  width: 0;
  height: 0;
  margin-right: var(--sp-1);
  border-left: 5px solid var(--muted);
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  transition: transform var(--t-fast);
}
.collapsible-arrow.open { transform: rotate(90deg); }
.collapsible-head:hover .collapsible-arrow { border-left-color: var(--text); }

/* 高度动画：0fr ↔ 1fr，内容多高动画就多高，不需要写死像素值 */
.collapsible-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--t-mid) ease;
}
.collapsible-body.open { grid-template-rows: 1fr; }
.collapsible-inner {
  min-height: 0;
  overflow: hidden;
  transition: visibility 0s linear var(--t-mid);
}
.collapsible-body.open .collapsible-inner { visibility: visible; transition: visibility 0s linear; }
/* 折叠后：移出 Tab 焦点链（否则键盘用户会 Tab 到看不见的按钮上） */
.collapsible-body:not(.open) .collapsible-inner { visibility: hidden; }
</style>
