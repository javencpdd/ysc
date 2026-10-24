<template>
  <!-- 全局唯一实例，挂在 App.vue 根部；业务组件只管 await askConfirm(...) -->
  <Teleport to="body">
    <Transition name="cd">
      <div
        v-if="state"
        class="cd-mask"
        @click.self="resolveConfirm(false)"
      >
        <div
          class="cd-card"
          :class="{ 'cd-danger': state.danger }"
          role="alertdialog"
          aria-modal="true"
          :aria-label="state.title"
        >
          <div class="cd-head">
            <span class="cd-icon" :class="state.danger ? 'danger' : 'info'">{{ state.danger ? '⚠' : 'i' }}</span>
            <h4 class="cd-title">{{ state.title }}</h4>
          </div>

          <div class="cd-body">
            <p v-if="state.message" class="cd-msg">{{ state.message }}</p>
            <p v-if="state.detail" class="cd-detail">{{ state.detail }}</p>
          </div>

          <div class="cd-actions">
            <button
              ref="cancelEl"
              type="button"
              class="btn-ghost"
              @click="resolveConfirm(false)"
            >{{ state.cancelText }}</button>
            <button
              ref="okEl"
              type="button"
              :class="state.danger ? 'btn-danger' : 'btn-primary'"
              @click="resolveConfirm(true)"
            >{{ state.confirmText }}</button>
          </div>

          <p v-if="state.danger" class="cd-foot">
            按 Esc 取消；危险操作不响应回车确认，需手动点击右侧按钮。
          </p>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { confirmState, resolveConfirm } from '../composables/useConfirm.js'

const state = computed(() => confirmState.value)
const cancelEl = ref(null)
const okEl = ref(null)

// 焦点策略：危险操作聚焦「取消」（手滑回车不会执行），
// 普通操作聚焦「确认」（减少一次 Tab）。
watch(() => (state.value && state.value.id) || 0, async (id) => {
  if (!id) return
  await nextTick()
  const target = state.value && state.value.danger ? cancelEl.value : okEl.value
  if (target && target.focus) target.focus()
})

function onKeydown (ev) {
  if (!state.value) return
  if (ev.key === 'Escape') {
    ev.preventDefault()
    resolveConfirm(false)
    return
  }
  // 危险操作不绑定回车，避免"顺手一敲"就执行
  if (ev.key === 'Enter' && !state.value.danger) {
    ev.preventDefault()
    resolveConfirm(true)
  }
}

onMounted(() => { document.addEventListener('keydown', onKeydown) })
onUnmounted(() => { document.removeEventListener('keydown', onKeydown) })
</script>

<style scoped>
.cd-mask {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-4);
  background: rgba(6, 11, 16, 0.66);
  backdrop-filter: blur(2px);
}

.cd-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 440px;
  /* 文案再长也不出屏：小屏时卡片整体不超视口，内部正文区滚动，按钮始终可见 */
  max-height: calc(100vh - 2 * var(--sp-4));
  padding: var(--sp-4);
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-lg);
  box-shadow: var(--sh-3);
}

/* 危险操作：整卡描边转红，与蓝色（普通确认）在远距离也能区分 */
.cd-card.cd-danger { border-color: var(--danger-line); }

.cd-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
}

.cd-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  font-size: var(--fs-14);
  border-radius: 50%;
  flex: 0 0 auto;
}
.cd-icon.danger { color: var(--danger); background: var(--danger-soft); }
.cd-icon.info { color: var(--accent); background: var(--accent-soft); }

.cd-title {
  margin: 0;
  font-size: var(--fs-15);
  font-weight: 600;
  color: var(--text-strong);
  line-height: 1.4;
}

.cd-body { margin-bottom: var(--sp-4); overflow: auto; }

.cd-msg {
  margin: 0;
  font-size: var(--fs-13);
  line-height: 1.7;
  color: var(--text);
  white-space: pre-line;
  word-break: break-word;
}

.cd-detail {
  margin: var(--sp-2) 0 0;
  padding: var(--sp-2);
  font-size: var(--fs-12);
  line-height: 1.65;
  color: var(--muted);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  white-space: pre-line;
}

.cd-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
}

.cd-foot {
  margin: var(--sp-2) 0 0;
  font-size: var(--fs-11);
  color: var(--muted);
  text-align: right;
}

/* 进出场动画 */
.cd-enter-active, .cd-leave-active { transition: opacity var(--t); }
.cd-enter-from, .cd-leave-to { opacity: 0; }
.cd-enter-active .cd-card, .cd-leave-active .cd-card { transition: transform var(--t); }
.cd-enter-from .cd-card, .cd-leave-to .cd-card { transform: translateY(8px) scale(0.98); }

@media (max-width: 560px) {
  .cd-actions { flex-direction: column-reverse; }
  .cd-actions button { width: 100%; }
}
</style>
