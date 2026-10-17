<template>
  <header style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px">
    <h2 style="margin: 0">M20 Pro 机器人控制台</h2>
    <div style="color: var(--muted); font-size: 12px">
      数据源 {{ svc.data_source || '—' }} · 推送 {{ svc.push_hz || 10 }}Hz ·
      WS 客户端 {{ svc.ws_clients ?? 0 }} ·
      <span :style="{ color: connected ? 'var(--ok)' : 'var(--danger)' }">
        {{ connected ? '链路在线' : '链路断开' }}
      </span>
      <!-- 心跳（遥测）让渡：停发 = 主动放弃状态推送。未暂停时才显示入口 -->
      <button v-if="!heartbeatPaused" class="hb-btn" :class="{ danger: hbConfirming }"
              type="button" @click="pauseHeartbeat">
        {{ hbConfirming ? '再点一次确认暂停' : '暂停心跳' }}
      </button>
    </div>
  </header>

  <!-- 降级：数据停更必须显式暴露，绝不把旧数据当新数据展示（PLAN §6.2） -->
  <!-- 优先级最高：主动暂停遥测是"操作者有意为之"，与链路故障提示语义相反，
       不能显示成红色告警把用户吓到，也不能让"没数据"被误解成"车没事" -->
  <div v-if="heartbeatPaused" class="banner motion-running">
    ⚠ 心跳已<b>主动暂停</b> —— 遥测失效（<b>非故障</b>）：看不到机器人状态了，
    但它可能仍在运动。控制指令已被服务端禁止（软急停除外）。
    <button class="hb-btn hb-resume" type="button" @click="resumeHeartbeat">恢复心跳</button>
  </div>
  <div v-else-if="!connected" class="banner">
    ⚠ 数据已停更 {{ sinceSeconds.toFixed(1) }}s —— 以下数值为最后收到的快照，可能已过期
  </div>
  <div v-else-if="staleTopics.length" class="banner" style="background: var(--warn)">
    部分数据停更：{{ staleTopics.join('、') }}（对应面板已置灰）
  </div>

  <!-- 定时移动跨标签提示：切到别的标签也看得见倒计时（运动在后端跑，不随标签切换中断） -->
  <div v-if="timedActive" class="banner motion-running">
    ⚠ 定时移动进行中：剩余 {{ timedRemaining.toFixed(1) }}s / 共 {{ timedTotal.toFixed(1) }}s
    —— 运动在后端执行，切标签不会中断；要中止请回「运动控制」标签点「中止」
  </div>

  <!-- 标签页（参考 lite3 monitor）：
       · 四个面板按"只读遥测 / 只读视频 / 只读 GPS / 写方向控制"分层，写方向放最后并用警示色；
       · 刻意不写 localStorage 记住上次标签：每次加载都回到只读的「传感器监控」，
         避免重新打开页面直接落在写方向页上误触指令（lite3 同款取舍）。 -->
  <nav class="tabs">
    <button class="tab" :class="{ active: tab === 'monitor' }" type="button"
            @click="tab = 'monitor'">传感器监控</button>
    <button class="tab" :class="{ active: tab === 'video' }" type="button"
            @click="tab = 'video'">相机画面</button>
    <!-- GPS 是只读遥测，放在写方向的「运动控制」之前 -->
    <button class="tab" :class="{ active: tab === 'gps' }" type="button"
            @click="tab = 'gps'">GPS 定位</button>
    <button class="tab risk" :class="{ active: tab === 'motion' }" type="button"
            @click="tab = 'motion'">
      <span class="risk-dot" />
      运动控制
      <span v-if="timedActive" class="tab-badge">{{ Math.ceil(timedRemaining) }}s</span>
    </button>
    <!-- 机器人设置：改的是整车行为与网络配置，风险不低于运动控制，排在它后面 -->
    <button class="tab risk" :class="{ active: tab === 'config' }" type="button"
            @click="tab = 'config'">
      <span class="risk-dot" />
      机器人设置
    </button>
  </nav>

  <!-- 三个面板一律用 v-show 而非 v-if：切换只改可见性、不卸载组件。
       · VideoPanel.onUnmounted 会拆掉全部取流（WebRTC/HLS 重连要 0.3~2s）；
       · MotionPanel 的定时轮询 / 看门狗状态同理，卸载会让倒计时断更；
       · 副作用（可接受）：隐藏的视频流仍在解码，切回是瞬时无缝的。 -->
  <div v-show="tab === 'monitor'" class="pane">
    <RobotStatus :topic="topic" :is-stale="isStale" />
    <JointPanel :topic="topic" :is-stale="isStale" />
  </div>

  <!-- 相机页也拿到整车状态：相机随车供电，休眠时没有画面（2026-10-17 取证：
       进入休眠会依次关 VIDEO_POWER / JOINTS_POWER / LED_FILL / FAN_SPEED）。
       就地给「唤醒整车」入口，省得为了开相机还要切到运动控制页。 -->
  <div v-show="tab === 'video'" class="pane">
    <VideoPanel
      :device="topic('device')"
      :basic="topic('basic')"
      :control="control"
      :send-command="sendCommand"
    />
  </div>

  <!-- GPS：呈现 M20 上报的 GPS 数据包 + GPS 供电开关（1101/3，2026-10-17 抓包破解） -->
  <div v-show="tab === 'gps'" class="pane">
    <GpsPanel
      :device="topic('device')"
      :control="control"
      :send-command="sendCommand"
    />
  </div>

  <div v-show="tab === 'motion'" class="pane">
    <div class="risk-warn">
      运动控制为<b>写方向</b>通道：下发的轴指令会直接驱动机器人。请确认周围人员已撤离、
      机器人已站立且处于空旷场地，异常时优先点「软急停」。
      <br />切到其他标签时摇杆会<b>立即自动零位停止</b>（不等停更超时）；
      <b>定时移动会在后台继续跑到点</b>（顶部黄条与标签上的倒计时实时可见）。
    </div>
    <MotionPanel
      :control="control"
      :send-command="sendCommand"
      :send-axis="sendAxis"
      :send-timed-axis="sendTimedAxis"
      :stop-axis="stopAxis"
      :estop="estop"
      :clear-estop="clearEstop"
      :enable-control="enableControl"
      :disable-control="disableControl"
      :renew-lease="renewLease"
      :refresh-control="refreshControl"
      :watchdog="watchdog"
      :motion="topic('motion')"
      :basic="topic('basic')"
      :device="topic('device')"
      :active="tab === 'motion'"
    />
  </div>

  <!-- 机器人设置：补光灯 / 首启回零 / 休眠 / WiFi 热点。
       同样用 v-show —— 它需要 2Hz 设备帧里的补光灯状态，卸载会丢数据源。 -->
  <div v-show="tab === 'config'" class="pane">
    <div class="risk-warn">
      本页<b>会改变整车行为与网络配置</b>：
      「立即休眠」会让机器人趴下并断电；改 WiFi 热点会让已连设备掉线。
      改热点不会动上行链路（我们 SSH 的通路），但两者共用一块射频，脚本会自动复查并在失败时回滚。
    </div>
    <RobotConfigPanel
      :control="control"
      :device="topic('device')"
    />
  </div>

  <!-- 指令报文记录（全局）：任何标签页发出的指令都能就地看到响应。
       默认收起，只占一行；展开后才轮询后端。 -->
  <PacketLogPanel />
</template>

<script setup>
import { computed, ref } from 'vue'
import RobotStatus from './components/RobotStatus.vue'
import JointPanel from './components/JointPanel.vue'
import GpsPanel from './components/GpsPanel.vue'
import MotionPanel from './components/MotionPanel.vue'
import VideoPanel from './components/VideoPanel.vue'
import RobotConfigPanel from './components/RobotConfigPanel.vue'
import PacketLogPanel from './components/PacketLogPanel.vue'
import { useRobotState } from './composables/useRobotState.js'

const s = useRobotState()
const {
  snapshot, topics, connected, staleTopics, sinceSeconds, control, watchdog,
  topic, isStale, sendCommand, sendAxis, sendTimedAxis, stopAxis, estop, clearEstop,
  enableControl, disableControl, renewLease, refreshControl, sendHeartbeat
} = s

const svc = computed(() => (snapshot.value && snapshot.value.service) || {})

/** 当前标签：monitor=传感器监控 / video=相机画面 / motion=运动控制（写方向） */
const tab = ref('monitor')

// 定时移动的跨标签可见性：后端在跑，任何标签都得让用户知道"车还在动"
const timedActive = computed(() => !!(watchdog.value && watchdog.value.timed_active))
const timedRemaining = computed(() => Number((watchdog.value && watchdog.value.timed_remaining) || 0))
const timedTotal = computed(() => Number((watchdog.value && watchdog.value.timed_total) || 0))

// ------------------------------------------- 心跳（遥测）让渡（2026-10-16 加）
// 与 useRobotState 里那个前端自算的 degraded（链路质量）不是一回事：这里读的是
// 后端 ServiceSnapshot.degraded_reason，语义是"操作者主动放弃了遥视"。
const DEGRADED_HEARTBEAT_PAUSED = 'heartbeat_paused'   // 与后端 main.DEGRADED_HEARTBEAT_PAUSED 对齐
const heartbeatPaused = computed(() =>
  !!(svc.value.degraded && svc.value.degraded_reason === DEGRADED_HEARTBEAT_PAUSED))
const hbConfirming = ref(false)

async function pauseHeartbeat () {
  // 两步确认（不弹窗）：停心跳 = 放弃遥测，而指令链路仍可达，属于危险方向
  if (!hbConfirming.value) { hbConfirming.value = true; return }
  hbConfirming.value = false
  const res = await sendHeartbeat(true, true)
  if (!res || !res.ok) hbConfirming.value = false
}

async function resumeHeartbeat () {
  // 恢复视野是安全动作，不需要二次确认
  await sendHeartbeat(false)
}
</script>

<style scoped>
.tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  padding: 4px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}

.tab {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  color: var(--muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
}

.tab:hover {
  color: var(--text);
  background: var(--panel-2);
  border-color: var(--line);
}

.tab.active {
  color: #fff;
  background: var(--accent);
  border-color: var(--accent);
}

/* 运动控制是写方向入口：激活态用警示色而非主色（与 lite3 monitor 一致） */
.tab.risk.active {
  background: #b45309;
  border-color: #b45309;
}

.risk-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--danger);
}

/* 定时移动进行中：标签上的倒计时角标 */
.tab-badge {
  padding: 1px 7px;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: #fff;
  background: var(--danger);
  border-radius: 999px;
}

/* 写方向页顶部警示条 */
.risk-warn {
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 13px;
  line-height: 1.7;
  color: #fcd34d;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid var(--warn);
  border-radius: 8px;
}

/* "定时移动进行中"全局提示：用警示色，与上面红色/琥珀色的数据停更条区分 */
.banner.motion-running {
  background: #b45309;
}

/* 心跳让渡按钮（顶栏小按钮 + 横幅内的恢复按钮共用） */
.hb-btn {
  margin-left: 10px;
  padding: 3px 10px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--muted);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 5px;
}

.hb-btn:hover {
  color: var(--text);
  border-color: var(--accent);
}

.hb-btn.danger {
  color: #fff;
  background: #7f1d1d;
  border-color: #b91c1c;
}

.hb-resume {
  margin-left: 12px;
  color: #fff;
  background: #b45309;
  border-color: #fbbf24;
}
</style>
