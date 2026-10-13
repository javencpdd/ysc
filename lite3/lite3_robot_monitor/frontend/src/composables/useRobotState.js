/**
 * 机器人状态数据源。
 *
 * 统一在这里完成 WebSocket 订阅、REST 轮询与历史缓冲，
 * 页面组件只负责渲染，不关心数据来源。
 */

import { ref, shallowRef, onMounted, onUnmounted } from 'vue'
import { StateSocket, fetchRaw, fetchStatus } from '../api/index.js'
import { toast } from './useToast.js'

/** IMU 曲线窗口：保留 30 秒 @10Hz */
const HISTORY_POINTS = 300

export function useRobotState() {
  /** 0x0901 机器人综合状态 */
  const robotState = shallowRef(null)
  /** 0x0902 关节角度 */
  const jointAngle = shallowRef(null)
  /** 0x0903 关节角速度 */
  const jointVelocity = shallowRef(null)
  /** 未支持消息码 */
  const others = shallowRef([])
  /** IMU 历史数据（用于 ECharts） */
  const history = ref([])
  /** WebSocket 连接状态：connecting | open | closed */
  const wsStatus = ref('connecting')
  /** 服务端运行状态 */
  const serviceStatus = shallowRef(null)
  /** 原始报文列表 */
  const rawPackets = ref([])
  /** 最近一次收到数据的时间（前端本地 ms） */
  const lastPacketAt = ref(0)
  /**
   * 后端 REST 是否不可达。
   * 关键：/api/status 拉取失败时若保留上一次的结果，页面会继续显示旧的 "Online"
   * 和旧的计数，用户会误以为一切正常。这里显式标记不可达，供 UI 降级显示。
   */
  const apiError = ref(false)
  /** 连续失败次数：达到阈值才判定不可达，避免单次网络抖动误报 */
  let statusFailures = 0

  let socket = null
  let statusTimer = null
  let rawTimer = null

  /** 处理服务端推送的快照 */
  function handleSnapshot(payload) {
    if (!payload || typeof payload !== 'object') return
    if (payload.robot_state) {
      robotState.value = payload.robot_state
      const imu = payload.robot_state.imu || {}
      const arr = history.value
      arr.push({
        t: Date.now(),
        roll: imu.roll ?? 0,
        pitch: imu.pitch ?? 0,
        yaw: imu.yaw ?? 0
      })
      if (arr.length > HISTORY_POINTS) arr.splice(0, arr.length - HISTORY_POINTS)
      history.value = arr.slice()
    }
    if (payload.joint_angle) jointAngle.value = payload.joint_angle
    if (payload.joint_velocity) jointVelocity.value = payload.joint_velocity
    if (payload.others) others.value = payload.others
    lastPacketAt.value = Date.now()
  }

  /** 拉取服务运行状态（1Hz，用于页面顶部状态灯与统计） */
  async function refreshStatus() {
    try {
      serviceStatus.value = await fetchStatus()
      if (statusFailures !== 0) statusFailures = 0
      // 从不可达状态恢复时提示一次，让用户知道链路已自愈
      if (apiError.value) {
        apiError.value = false
        toast.success('后端服务已恢复连接')
      }
    } catch (err) {
      statusFailures += 1
      // 连续 2 次失败才判定不可达：单次失败更可能是瞬时抖动
      if (statusFailures >= 2 && !apiError.value) {
        apiError.value = true
        toast.error('后端服务不可达，页面状态可能已过期')
      }
      console.warn('[useRobotState] 获取服务状态失败', err)
    }
  }

  /** 拉取原始报文摘要（0.5Hz，避免频繁请求影响实时链路） */
  async function refreshRaw() {
    try {
      const data = await fetchRaw(20)
      rawPackets.value = data.items || []
    } catch (err) {
      console.warn('[useRobotState] 获取原始报文失败', err)
    }
  }

  onMounted(() => {
    socket = new StateSocket({
      onSnapshot: handleSnapshot,
      onStatus: (s) => {
        wsStatus.value = s
      }
    })
    socket.connect()

    refreshStatus()
    refreshRaw()
    statusTimer = setInterval(refreshStatus, 1000)
    rawTimer = setInterval(refreshRaw, 2000)
  })

  onUnmounted(() => {
    socket?.close()
    clearInterval(statusTimer)
    clearInterval(rawTimer)
  })

  /**
   * 机器人链路是否在线。
   * 注意：后端不可达时 serviceStatus 是最后一次成功的快照，其值不可信，
   * 必须按离线处理，否则会出现"服务已挂、页面仍显示 Online"的误导。
   */
  const connected = () => Boolean(!apiError.value && serviceStatus.value?.connected)

  return {
    robotState,
    jointAngle,
    jointVelocity,
    others,
    history,
    wsStatus,
    serviceStatus,
    rawPackets,
    lastPacketAt,
    apiError,
    connected,
    refreshRaw,
    refreshStatus,
    ping: () => socket?.ping()
  }
}
