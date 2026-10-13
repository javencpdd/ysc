<script setup>
/**
 * App.vue
 * Lite3 Robot Monitor 主面板。
 *
 * 布局自上而下：
 *   顶部标题栏 + 服务概要
 *   → RobotStatus  机器人综合状态
 *   → IMUChart / Position  姿态与位姿、速度
 *   → JointPanel   12 个关节
 *   → RawPacket    原始报文
 */
import { computed, ref, onMounted, onUnmounted } from 'vue'
import RobotStatus from './components/RobotStatus.vue'
import IMUChart from './components/IMUChart.vue'
import JointPanel from './components/JointPanel.vue'
import RawPacket from './components/RawPacket.vue'
import SentPacket from './components/SentPacket.vue'
import RosInfoTip from './components/RosInfoTip.vue'
import ControlPanel from './components/ControlPanel.vue'
import ToastHost from './components/ToastHost.vue'
import { useRobotState } from './composables/useRobotState.js'
import { toast } from './composables/useToast.js'
import { clearRaw } from './api/index.js'

const {
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
  refreshRaw
} = useRobotState()

/** 顶部标题栏右侧的服务概要 */
const summary = computed(() => {
  const s = serviceStatus.value
  if (!s) return []
  // data_source / udp_mode 是排障的关键字段：udp_mode=sniff 才说明没有占用 43897
  return [
    { label: '数据源', value: s.data_source || '-' },
    { label: 'UDP 模式', value: s.udp_mode || '-' },
    { label: 'UDP', value: `${s.udp_host || '0.0.0.0'}:${s.udp_port}` },
    { label: '推送频率', value: `${s.push_hz} Hz` },
    { label: '已接收', value: s.packets_received },
    { label: 'WS 连接', value: s.ws_clients }
  ]
})

/** 世界坐标系位置（x, y, yaw） */
const position = computed(() => robotState.value?.position || { x: 0, y: 0, yaw: 0 })
/** 世界坐标系速度 */
const velocity = computed(() => robotState.value?.velocity || { x: 0, y: 0, yaw: 0 })
/** 机体系速度 */
const velocityBody = computed(() => robotState.value?.velocity_body || { x: 0, y: 0, yaw: 0 })
/** IMU 加速度 */
const acc = computed(() => robotState.value?.imu || {})

/** 通用数值格式化 */
const fmt = (v, digits = 3) => (typeof v === 'number' ? v.toFixed(digits) : '--')

/** 每秒滴答：驱动"距上次更新"这类相对时间重算 */
const now = ref(Date.now())
let tickTimer = null
onMounted(() => {
  tickTimer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})
onUnmounted(() => {
  if (tickTimer) clearInterval(tickTimer)
})

/** 距上一次收到数据的秒数；从未收到过则为 null */
const staleSeconds = computed(() => {
  const t = lastPacketAt.value
  if (!t) return null
  return Math.max(0, Math.round((now.value - t) / 1000))
})

/**
 * 链路健康度。
 * 此前页面只有 connected 一个布尔量，把三种完全不同的故障显示成同一句文案：
 *   down  后端 REST 不可达（此时 serviceStatus 已是过期快照）
 *   warn  WebSocket 未连接 / 数据更新延迟
 *   off   长时间无任何数据
 *   ok    正常
 */
const health = computed(() => {
  if (apiError.value) {
    return {
      level: 'down',
      short: '后端不可达',
      text: '后端服务不可达，页面数据可能已过期（正在自动重试）'
    }
  }
  if (wsStatus.value !== 'open') {
    return { level: 'warn', short: 'WS 重连中', text: 'WebSocket 未连接，正在自动重连' }
  }
  const gap = staleSeconds.value
  if (gap === null) {
    return {
      level: 'off',
      short: 'Offline',
      text: '未检测到机器人数据，请确认 Lite3 已上电并指向本机 UDP 端口'
    }
  }
  if (gap >= 10) {
    return {
      level: 'off',
      short: `停滞 ${gap}s`,
      text: `数据已停止更新 ${gap} 秒，请检查顶部数据源模式（udp_mode）与机器人链路`
    }
  }
  if (gap >= 3) {
    return { level: 'warn', short: `延迟 ${gap}s`, text: `数据更新延迟 ${gap} 秒` }
  }
  if (!connected()) {
    return { level: 'warn', short: '链路未确认', text: '后端尚未确认机器人链路在线' }
  }
  return {
    level: 'ok',
    short: 'Online',
    text: `数据链路正常 · 最近更新 ${gap} 秒前 · WebSocket ${wsStatus.value}`
  }
})

/**
 * 当前页面标签：
 *   monitor  监控页（只读遥测：姿态/位姿/关节/原始报文）
 *   console  操作台（写方向控制，风险操作）
 *
 * 刻意不写 localStorage 记住上次标签：每次加载都回到监控页，
 * 避免重新打开页面时直接落在操作台上、误触写方向指令。
 */
const tab = ref('monitor')

/** 当前生效数据源模式：ros / sniff / bind / none（决定 ROS 提示是否有意义） */
const dataSource = computed(() => serviceStatus.value?.data_source || '')
/** 数据是否确实由 ros_bridge 转发（ros_bridge_node 会打上 source.ip = 'ros_bridge'） */
const fromRos = computed(() => robotState.value?.source?.ip === 'ros_bridge')

async function handleClear() {
  try {
    await clearRaw()
    await refreshRaw()
    toast.success('已清空原始报文缓存')
  } catch (err) {
    console.warn('[App] 清空原始报文失败', err)
    toast.error('清空原始报文失败：后端不可达或接口异常')
  }
}
</script>

<template>
  <div class="page">
    <header class="topbar">
      <div class="brand">
        <h1>Lite3 Robot Monitor</h1>
        <p>四足机器人 UDP 状态实时监控面板</p>
      </div>
      <div class="summary">
        <div v-for="item in summary" :key="item.label" class="summary-item">
          <span class="k">{{ item.label }}</span>
          <span class="v mono">{{ item.value }}</span>
        </div>
        <div class="conn" :class="health.level">
          <span class="dot" />
          {{ health.short }}
        </div>
      </div>
    </header>

    <nav class="tabs">
      <button
        class="tab"
        :class="{ active: tab === 'monitor' }"
        type="button"
        @click="tab = 'monitor'"
      >
        监控页面
      </button>
      <button
        class="tab risk"
        :class="{ active: tab === 'console' }"
        type="button"
        @click="tab = 'console'"
      >
        <span class="risk-dot" />
        操作台
      </button>
    </nav>

    <main class="layout">
      <RobotStatus :state="robotState" :status="serviceStatus" :ws-status="wsStatus" />

      <template v-if="tab === 'monitor'">
        <div class="row">
          <IMUChart :history="history" />

          <section class="card metrics">
            <div class="card-title">
              <span>Position &amp; Velocity</span>
              <span class="sub">世界系 / 机体系</span>
            </div>

            <div class="metric-group">
              <div class="group-title">
              Position (world)
              <RosInfoTip area="odom" :source="dataSource" :from-ros="fromRos" />
            </div>
              <div class="metric-row">
                <div class="metric"><span>X</span><b class="mono">{{ fmt(position.x) }} m</b></div>
                <div class="metric"><span>Y</span><b class="mono">{{ fmt(position.y) }} m</b></div>
                <div class="metric"><span>Yaw</span><b class="mono">{{ fmt(position.yaw) }} rad</b></div>
              </div>
            </div>

            <div class="metric-group">
              <div class="group-title">
              Velocity (world)
              <RosInfoTip area="odom" :source="dataSource" :from-ros="fromRos" />
            </div>
              <div class="metric-row">
                <div class="metric"><span>Vx</span><b class="mono">{{ fmt(velocity.x) }} m/s</b></div>
                <div class="metric"><span>Vy</span><b class="mono">{{ fmt(velocity.y) }} m/s</b></div>
                <div class="metric"><span>ω</span><b class="mono">{{ fmt(velocity.yaw) }} rad/s</b></div>
              </div>
            </div>

            <div class="metric-group">
              <div class="group-title">
              Velocity (body)
              <RosInfoTip area="odom" :source="dataSource" :from-ros="fromRos" />
            </div>
              <div class="metric-row">
                <div class="metric"><span>Vx</span><b class="mono">{{ fmt(velocityBody.x) }} m/s</b></div>
                <div class="metric"><span>Vy</span><b class="mono">{{ fmt(velocityBody.y) }} m/s</b></div>
                <div class="metric"><span>ω</span><b class="mono">{{ fmt(velocityBody.yaw) }} rad/s</b></div>
              </div>
            </div>

            <div class="metric-group">
              <div class="group-title">
              IMU Acceleration
              <RosInfoTip area="imu" :source="dataSource" :from-ros="fromRos" />
            </div>
              <div class="metric-row">
                <div class="metric"><span>Ax</span><b class="mono">{{ fmt(acc.x_acc) }} m/s²</b></div>
                <div class="metric"><span>Ay</span><b class="mono">{{ fmt(acc.y_acc) }} m/s²</b></div>
                <div class="metric"><span>Az</span><b class="mono">{{ fmt(acc.z_acc) }} m/s²</b></div>
              </div>
            </div>

            <div v-if="others && others.length" class="metric-group">
              <div class="group-title">其他消息码</div>
              <div class="others">
                <span v-for="item in others" :key="item.code" class="chip mono">
                  {{ item.code }} · {{ item.length }} B
                </span>
              </div>
            </div>
          </section>
        </div>

        <JointPanel
          :angle="jointAngle"
          :velocity="jointVelocity"
          :data-source="dataSource"
          :from-ros="fromRos"
        />

        <!-- 收包（机器人 → 本机）只放在监控页 -->
        <RawPacket :packets="rawPackets" @refresh="refreshRaw" @clear="handleClear" />
      </template>

      <!-- 用 v-show 而不是 v-if：切换标签时 ControlPanel **不能**被卸载，
           否则会触发它的 onUnmounted，把正在运行的心跳停掉。 -->
      <div v-show="tab === 'console'" class="console-pane">
        <div class="console-warn">
          操作台为<strong>写方向</strong>通道：下发的指令会直接驱动机器人。
          请确认周围人员已撤离、机器人处于安全姿态，异常时优先点击「急停」。
        </div>

        <ControlPanel />

        <!-- 发包（本机 → 机器人）放在操作台：与"下发指令"同属写方向，语义上是一组。
             用的是 PacketMonitor 公共组件（SentPacket 只是它的预置配置封装）。 -->
        <SentPacket />
      </div>
    </main>

    <footer class="footer">
      <span :class="health.level === 'ok' ? 'ok' : 'warn'">{{ health.text }}</span>
    </footer>

    <ToastHost />
  </div>
</template>

<style scoped>
.page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px 22px 40px;
}

.topbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #ffffff, #eff4ff);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

.brand h1 {
  margin: 0;
  font-size: 22px;
  letter-spacing: -0.01em;
}

.brand p {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--text-sub);
}

.summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 18px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-item .k {
  font-size: 11px;
  color: #94a3b8;
}

.summary-item .v {
  font-size: 14px;
  font-weight: 600;
}

.conn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 999px;
}

.conn.on {
  color: #166534;
  background: #dcfce7;
}

.conn.off {
  color: #991b1b;
  background: #fee2e2;
}

.conn.warn {
  color: #92400e;
  background: #fef3c7;
}

.conn.down {
  color: #991b1b;
  background: #fee2e2;
}

.conn .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
  padding: 4px;
  background: #f1f5f9;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius);
}

.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 20px;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.tab:hover {
  background: #e2e8f0;
}

.tab.active {
  color: #ffffff;
  background: #2563eb;
}

/* 操作台是写方向入口，激活态用警示色而非主色 */
.tab.risk.active {
  color: #ffffff;
  background: #b45309;
}

.risk-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #dc2626;
}

.console-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.console-warn {
  padding: 11px 15px;
  font-size: 13px;
  line-height: 1.6;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fcd34d;
  border-radius: var(--radius);
}

.layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.row {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 16px;
}

@media (max-width: 1080px) {
  .row {
    grid-template-columns: 1fr;
  }
}

.metrics {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.group-title {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  background: #f8fafc;
  border: 1px solid #e6ecf3;
  border-radius: 8px;
}

.metric span {
  font-size: 11px;
  color: #94a3b8;
}

.metric b {
  font-size: 13px;
  font-weight: 600;
}

.others {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 3px 8px;
  font-size: 11px;
  color: #475569;
  background: var(--chip-bg);
  border-radius: 6px;
}

.footer {
  margin-top: 18px;
  font-size: 12px;
  color: var(--text-sub);
  text-align: center;
}

.footer .warn {
  color: #b45309;
}

.footer .ok {
  color: #166534;
}
</style>
