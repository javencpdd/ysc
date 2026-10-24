/**
 * 统一二次确认弹窗（2026-10-20 界面改造）。
 *
 * 为什么不用 window.confirm：
 *   · 原生弹窗样式与控制台深色主题割裂，且无法区分「危险程度」；
 *   · 文案一长就被截断，放不下"会发生什么 / 影响范围"这类必须说清的内容；
 *   · 无法给出统一的键盘与焦点行为。
 *
 * 设计约束（只动展示层，不动业务）：
 *   · 调用方式与 window.confirm 等价 —— `await askConfirm({...})` 返回 true / false，
 *     调用方的判断分支、后续接口调用一行不改；
 *   · 危险操作（danger=true）默认把焦点放在「取消」上，且回车不直接确认，
 *     降低误操作概率。
 */

import { ref } from 'vue'

/** 当前弹窗状态；为 null 表示无弹窗。ConfirmDialog 直接消费它。 */
export const confirmState = ref(null)

let seq = 0

/**
 * 弹出确认框。
 *
 * @param {object} options
 * @param {string} options.title        标题，动词开头，如「确认软急停？」
 * @param {string} options.message      主说明（会自动按 \n 换行）
 * @param {string} [options.detail]     次要说明（后果 / 影响范围）
 * @param {string} [options.confirmText] 确认按钮文案，默认「确认执行」
 * @param {string} [options.cancelText]  取消按钮文案，默认「取消」
 * @param {boolean} [options.danger]    是否为危险操作（红色确认按钮）
 * @returns {Promise<boolean>} 用户是否确认
 */
export function askConfirm (options) {
  return new Promise((resolve) => {
    // 理论上同一时刻只应有一个弹窗；真出现嵌套时把上一个按「取消」结掉，
    // 避免 Promise 悬挂导致按钮永远停在加载态。
    if (confirmState.value && confirmState.value.resolve) {
      confirmState.value.resolve(false)
    }
    seq += 1
    confirmState.value = {
      id: seq,
      title: (options && options.title) || '请确认操作',
      message: (options && options.message) || '',
      detail: (options && options.detail) || '',
      confirmText: (options && options.confirmText) || '确认执行',
      cancelText: (options && options.cancelText) || '取消',
      danger: !!(options && options.danger),
      resolve
    }
  })
}

/**
 * 关闭弹窗并给出结果。由 ConfirmDialog 调用。
 * @param {boolean} value true=确认 / false=取消
 */
export function resolveConfirm (value) {
  const cur = confirmState.value
  if (!cur) return
  confirmState.value = null
  cur.resolve(!!value)
}
