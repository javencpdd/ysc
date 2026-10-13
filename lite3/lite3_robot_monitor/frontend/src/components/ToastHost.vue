<script setup>
/**
 * ToastHost.vue
 * 全局通知渲染容器：挂载在 App 根节点，右下角浮层展示。
 */
import { toasts, dismiss } from '../composables/useToast.js'
</script>

<template>
  <div class="toast-host">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type">
      <span class="dot" />
      <span class="msg">{{ t.message }}</span>
      <button class="close" type="button" title="关闭" @click="dismiss(t.id)">×</button>
    </div>
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: min(380px, calc(100vw - 36px));
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.5;
  background: #ffffff;
  border: 1px solid #e6ecf3;
  border-radius: var(--radius, 10px);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.12);
}

.toast .dot {
  flex: none;
  width: 8px;
  height: 8px;
  margin-top: 6px;
  border-radius: 50%;
  background: currentColor;
}

.toast .msg {
  flex: 1;
  min-width: 0;
  word-break: break-word;
}

.toast .close {
  flex: none;
  padding: 0 2px;
  font-size: 15px;
  line-height: 1;
  color: #94a3b8;
  background: none;
  border: none;
  cursor: pointer;
}

.toast .close:hover {
  color: #475569;
}

.toast.info {
  color: #185fa5;
  border-color: #b5d4f4;
}

.toast.success {
  color: #166534;
  border-color: #c0dd97;
}

.toast.warn {
  color: #92400e;
  border-color: #f5c4b3;
}

.toast.error {
  color: #991b1b;
  border-color: #f7c1c1;
}
</style>
