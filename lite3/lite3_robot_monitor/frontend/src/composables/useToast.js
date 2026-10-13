/**
 * 全局轻量通知（toast）。
 *
 * 为什么需要它：此前所有接口失败都只在 console 里 warn，用户在页面上完全看不到反馈
 * （切换数据源失败、清空原始报文失败、后端不可达……），表现为"点了没反应"。
 *
 * 实现：模块级响应式队列（单例），任意组件 push，由 ToastHost 统一渲染，
 * 避免引入 pinia / provide-inject 之类的额外依赖。
 */

import { ref } from 'vue'

/** 当前展示中的通知队列 */
export const toasts = ref([])

let seq = 0

/** 入队一条通知 */
function push(message, type = 'info', timeout = 4000) {
  const id = ++seq
  toasts.value = [...toasts.value, { id, message, type }]
  if (timeout > 0) {
    setTimeout(() => dismiss(id), timeout)
  }
  return id
}

/** 关闭指定通知 */
export function dismiss(id) {
  toasts.value = toasts.value.filter((t) => t.id !== id)
}

export const toast = {
  info: (m, t) => push(m, 'info', t),
  success: (m, t) => push(m, 'success', t),
  warn: (m, t) => push(m, 'warn', t),
  /** 错误默认停留更久，避免用户错过 */
  error: (m, t) => push(m, 'error', t === undefined ? 6000 : t)
}
