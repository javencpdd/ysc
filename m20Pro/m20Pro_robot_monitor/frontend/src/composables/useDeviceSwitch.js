/**
 * 设备供电开关（1101/3）—— 前端封装（2026-10-17 抓包取证后落地）。
 *
 * 协议事实（见 backend/control/patrol_codec.py DEVICE_SWITCH_SPEC）：
 *   - 一条指令 1101/3，Items 的**键名**决定目标设备：Video/Lidar/GPS/LedHost/
 *     LedExt/LoadPower/FP/FanSpeed/GPSMode
 *   - 该指令只认厂商 App 的帧头 magic，故后端按指令自动切 magic，前端无感
 *   - "关闭"是不可逆操作：服务端要求 confirmed=true，且站立/RL 态禁关雷达
 *
 * 设计取舍：
 *   - confirmed 只在**用户确认过关闭**时才传 true —— 服务端那道闸是真实防线，
 *     不能被前端"顺手传 true"抹掉
 *   - 运动中禁关雷达由服务端判定并回 detail，前端只负责把 detail 摆出来
 *     （判定逻辑单一来源，避免两套语义漂移）
 */

import { ref } from 'vue'
import { askConfirm } from './useConfirm.js'

/** @param {{ sendCommand: Function|null }} props 由页面透传 */
export function useDeviceSwitch (props) {
  /** 正在处理的键，形如 'Video.Front' —— 用于按钮 loading 态 */
  const busy = ref('')
  /** 最近一次操作结果提示 */
  const msg = ref('')
  /** 最近一次失败原因（服务端 detail 优先） */
  const err = ref('')

  let clearTimer = null

  //: 最近**成功下发**的 Items（按设备键），带时间戳。
  //: 为什么需要：1101/3 是整键覆写，改一路必须带上另一路的值，而另一路的值只能
  //: 从 `props.device` 读 —— 那是 2Hz 上报，**点完立刻点另一路会读到旧值**，
  //: 于是把刚打开的那路又写回 0（服务端安全闸会拦住"关"的方向，表现为"点了没反应"）。
  //: 所以短时间内优先用"我们刚下发的值"，跨过一次上报周期。
  const lastSent = {}
  const LOCAL_TTL_MS = 6000

  function flash (text, isError) {
    msg.value = text || ''
    err.value = isError ? (text || '') : ''
    if (clearTimer) clearTimeout(clearTimer)
    if (text) {
      clearTimer = setTimeout(() => { msg.value = ''; err.value = '' }, 8000)
    }
  }

  /** 断电后果按设备分别说明（确认弹窗用，避免一句套话覆盖所有设备） */
  const POWER_OFF_DETAIL = {
    Video: '画面与推流会立即中断，需重新上电并点「重新连接」才恢复。',
    Lidar: '感知输入消失；站立 / RL 控制运动中关闭会被服务端拒绝。',
    GPS: '定位数据停止更新；与「GPS 时间同步」不是同一条指令，不影响时钟。',
    LedHost: '主机电源指示灯熄灭，不影响运动与感知。',
    LedExt: '外部负载指示灯熄灭。',
    LoadPower: '外部负载断电，挂载设备会停止工作。',
    FP: '对频模块断电，遥控器需重新对频。',
    FanSpeed: '散热风扇停转，长时间高负载运行请注意机体温度。'
  }

  function describe (key, side) {
    const names = {
      Video: '相机', Lidar: '雷达', GPS: 'GPS', LedHost: '主机电源指示灯',
      LedExt: '外部负载指示灯', LoadPower: '外部负载供电', FP: '对频模块',
      FanSpeed: '散热风扇'
    }
    const base = names[key] || key
    if (side === 'Front') return `${base}（前）`
    if (side === 'Back') return `${base}（后）`
    return base
  }

  /**
   * 应用一次设备开关。
   *
   * @param {string} key      Items 键名（Video / Lidar / GPS / ...）
   * @param {object} items    完整 Items，如 {"Video":{"Front":1,"Back":0}}
   * @param {string} side     可选，仅用于提示文案（'Front' | 'Back' | ''）
   * @param {boolean} turningOff 本次是否是"关闭"（决定要不要弹确认、传 confirmed）
   */
  async function apply (key, items, side = '', turningOff = false) {
    if (!props.sendCommand) {
      flash('本页未接入指令通道', true)
      return { ok: false, reason: 'NO_SENDER' }
    }
    const what = describe(key, side)

    if (turningOff) {
      // 统一走确认弹窗（原 window.confirm）：按设备给出**具体**后果，
      // 而不是对所有设备套同一句"会物理断电"。
      const ok = await askConfirm({
        title: `确认关闭${what}供电？`,
        message: '关闭后会物理断电，需重新开启才能恢复。',
        detail: POWER_OFF_DETAIL[key] || '对应部件将立即停止工作。',
        confirmText: '确认关闭供电',
        danger: true
      })
      if (!ok) return { ok: false, reason: 'CANCELLED' }
    }

    busy.value = side ? `${key}.${side}` : key
    try {
      // confirmed 仅在我们确实弹过确认时为 true —— 服务端那道闸必须保持有效
      const res = await props.sendCommand('device_switch', { items }, turningOff)
      if (res && res.ok) {
        lastSent[key] = { items, at: Date.now() }
        flash(`${turningOff ? '已关闭' : '已开启'}${what}供电`)
      } else {
        flash(`操作被拒：${(res && res.reason) || '未知'} ${(res && res.detail) || ''}`, true)
      }
      return res
    } catch (e) {
      flash('请求失败：' + (e && e.message ? e.message : e), true)
      return { ok: false, reason: 'EXCEPTION' }
    } finally {
      busy.value = ''
    }
  }

  /**
   * 单路开关（GPS / LedHost / ...）—— `wantOn` 是**目标状态**，不是"当前状态"。
   *
   * ⚠️ 命名刻意用 ``setXxx`` 而非 ``toggleXxx``：这个函数曾叫 ``toggleFlag`` 并
   * 接收"当前值"、内部取反，而调用方（状态+动作分离的开关组件）传的是**目标值**
   * → 点「开」实际发「关」（2026-10-17 真踩）。参数名与函数名一起改成"目标语义"，
   * 让同类误用在读代码时就能被看出来。
   */
  async function setFlag (key, wantOn) {
    return apply(key, { [key]: wantOn ? 1 : 0 }, '', !wantOn)
  }

  /**
   * 前后两路独立开关（Video / Lidar）—— `wantOn` 同样是**目标状态**。
   *
   * ⚠️ 必须把**另一路的当前值**一起带上：1101/3 是整键覆写，
   * 只写一路会把没点的那路默认成 0（= 顺带关掉）。
   *
   * @param {boolean|number} wantOn       想要这一路变成开还是关
   * @param {*} currentOther              另一路的**当前**值（可为 2 = 运行中，会归一成 1）
   */
  async function setPair (key, side, wantOn, currentOther) {
    const other = side === 'Front' ? 'Back' : 'Front'
    // 另一路优先取"我们刚下发的值"（见 lastSent 注释），否则才用上报值
    let otherNow = currentOther
    const cached = lastSent[key]
    if (cached && Date.now() - cached.at < LOCAL_TTL_MS
        && cached.items[key] && other in cached.items[key]) {
      otherNow = cached.items[key][other]
    }
    const items = { [key]: { Front: 0, Back: 0 } }
    items[key][side] = wantOn ? 1 : 0
    items[key][other] = Number(otherNow) ? 1 : 0
    return apply(key, items, side, !wantOn)
  }

  return { busy, msg, err, flash, apply, setFlag, setPair }
}
