<template>
  <div class="app-shell">
    <!-- 顶栏：左侧身份，右侧链路健康度。信息分层：标题 > 指标 > 状态 -->
    <header class="app-header">
      <div class="app-brand">
        <span class="app-logo">M20</span>
        <div class="app-brand-text">
          <h1 class="app-title">M20 Pro 机器人控制台</h1>
          <p class="app-subtitle">实时监控 · 运动控制 · 机器人设置</p>
        </div>
      </div>

      <div class="app-meta">
        <span class="meta-item" title="后端当前采用的数据来源（UDP 直连 / 回放等）">
          <span class="meta-label">数据源</span>
          <b class="meta-value">{{ svc.data_source || '—' }}</b>
        </span>
        <span class="meta-item" title="后端每秒向本页推送状态快照的次数">
          <span class="meta-label">状态推送频率</span>
          <b class="meta-value num">{{ svc.push_hz || 10 }} Hz</b>
        </span>
        <span class="meta-item" title="正在接收实时数据的终端数（按 WebSocket 连接计，一个浏览器页面算一个终端）">
          <span class="meta-label">在线终端</span>
          <b class="meta-value num">{{ svc.ws_clients ?? 0 }}</b>
        </span>

        <span class="pill" :class="connected ? 'pill-ok' : 'pill-bad'">
          <span class="status-dot" :class="connected ? 'ok pulse' : 'bad'" />
          {{ connected ? '实时链路在线' : '实时链路已断开' }}
        </span>

        <!-- 状态推送（遥测心跳）让渡：停发 = 主动放弃状态推送。未暂停时才显示入口 -->
        <button
          v-if="!heartbeatPaused"
          class="btn-sm"
          :class="{ 'btn-danger': hbConfirming }"
          type="button"
          :title="hbPauseTip"
          @click="pauseHeartbeat"
        >{{ hbConfirming ? '再点一次确认暂停' : '暂停状态推送' }}</button>
      </div>
    </header>

    <!-- 降级：数据停更必须显式暴露，绝不把旧数据当新数据展示（PLAN §6.2） -->
    <!-- 优先级最高：主动暂停遥测是"操作者有意为之"，与链路故障提示语义相反，
         不能显示成红色告警把用户吓到，也不能让"没数据"被误解成"车没事" -->
    <div class="banner-stack">
      <div v-if="heartbeatPaused" class="banner is-motion">
        <span class="banner-icon">⏸</span>
        <div class="banner-text">
          <b>状态推送已主动暂停</b> —— 遥测失效（<b>非故障</b>）：本页看不到机器人状态了，
          但它可能仍在运动。控制指令已被服务端禁止（软急停除外）。
        </div>
        <button class="btn-sm btn-primary" type="button" @click="resumeHeartbeat">恢复状态推送</button>
      </div>
      <div v-else-if="!connected" class="banner is-danger">
        <span class="banner-icon">⚠</span>
        <div class="banner-text">
          数据已停更 <b class="num">{{ sinceSeconds.toFixed(1) }}s</b> ——
          以下数值为最后收到的快照，<b>可能已过期</b>
        </div>
      </div>
      <div v-else-if="staleTopics.length" class="banner is-warn">
        <span class="banner-icon">⚠</span>
        <div class="banner-text">
          部分数据停更：{{ staleTopics.join('、') }}（对应面板已置灰）
        </div>
      </div>

      <!-- 定时移动跨标签提示：切到别的标签也看得见倒计时（运动在后端跑，不随标签切换中断） -->
      <div v-if="timedActive" class="banner is-motion">
        <span class="banner-icon">▶</span>
        <div class="banner-text">
          <b>定时移动进行中</b>：剩余 <b class="num">{{ timedRemaining.toFixed(1) }}s</b>
          / 共 <b class="num">{{ timedTotal.toFixed(1) }}s</b>
          —— 运动在后端执行，切标签不会中断；要中止请回「运动控制」标签点「中止移动」
        </div>
      </div>
    </div>

    <!-- 标签页（参考 lite3 monitor）：
         · 四个面板按"只读遥测 / 只读视频 / 只读 GPS / 写方向控制"分层，写方向放最后并用警示色；
         · 刻意不写 localStorage 记住上次标签：每次加载都回到只读的「传感器监控」，
           避免重新打开页面直接落在写方向页上误触指令（lite3 同款取舍）。 -->
    <nav class="tabs" role="tablist" aria-label="功能分区">
      <button class="tab" :class="{ active: tab === 'monitor' }" type="button"
              role="tab" :aria-selected="tab === 'monitor'"
              title="只读：机器人基础状态、电池、关节与异常码"
              @click="tab = 'monitor'">传感器监控</button>
      <button class="tab" :class="{ active: tab === 'video' }" type="button"
              role="tab" :aria-selected="tab === 'video'"
              title="只读：前后双路实时画面、相机供电与取流控制"
              @click="tab = 'video'">相机画面</button>
      <!-- GPS 是只读遥测，放在写方向的「运动控制」之前 -->
      <button class="tab" :class="{ active: tab === 'gps' }" type="button"
              role="tab" :aria-selected="tab === 'gps'"
              title="只读：GPS 定位数据、供电开关与卫星系统选择"
              @click="tab = 'gps'">GPS 定位</button>
      <button class="tab risk" :class="{ active: tab === 'motion' }" type="button"
              role="tab" :aria-selected="tab === 'motion'"
              title="写方向：可驱动机器人运动，需先「开启控制」并取得控制权"
              @click="tab = 'motion'">
        <span class="risk-dot" />
        运动控制
        <span v-if="timedActive" class="tab-badge num">{{ Math.ceil(timedRemaining) }}s</span>
      </button>
      <!-- 机器人设置：改的是整车行为与网络配置，风险不低于运动控制，排在它后面 -->
      <button class="tab risk" :class="{ active: tab === 'config' }" type="button"
              role="tab" :aria-selected="tab === 'config'"
              title="写方向：修改补光灯 / 首启回零 / 休眠 / WiFi 热点等整车设置"
              @click="tab = 'config'">
        <span class="risk-dot" />
        机器人设置
      </button>
    </nav>

    <!-- 三个面板一律用 v-show 而非 v-if：切换只改可见性、不卸载组件。
         · MotionPanel 的定时轮询 / 看门狗状态同理，卸载会让倒计时断更；
         · 副作用（可接受）：隐藏的视频流仍在解码，切回是瞬时无缝的。
         ⚠️ 2026-10-18 修订：**视频这条不再是"可接受的副作用"** —— v-show 不卸载
         + 停流写在 onUnmounted，导致控制台一开着两路视频就一直在拉，
         不管你停在哪个标签页（实测两路约 100KB/s 上行，196 走 WiFi 上联）。
         现在 VideoPanel 自己收 `active`  prop，切走标签页/切走浏览器窗口/
         手动点「暂停拉流」都会真拆流（WHEP DELETE + close PC，HLS destroy）。 -->
    <div v-show="tab === 'monitor'" class="pane" role="tabpanel" aria-label="传感器监控">
      <RobotStatus :topic="topic" :is-stale="isStale" />
      <JointPanel :topic="topic" :is-stale="isStale" />
    </div>

    <!-- 相机页也拿到整车状态：相机随车供电，休眠时没有画面（2026-10-17 取证：
         进入休眠会依次关 VIDEO_POWER / JOINTS_POWER / LED_FILL / FAN_SPEED）。
         就地给「唤醒整车」入口，省得为了开相机还要切到运动控制页。 -->
    <div v-show="tab === 'video'" class="pane" role="tabpanel" aria-label="相机画面">
      <VideoPanel
        :device="topic('device')"
        :basic="topic('basic')"
        :control="control"
        :send-command="sendCommand"
        :active="tab === 'video'"
      />
    </div>

    <!-- GPS：呈现 M20 上报的 GPS 数据包 + GPS 供电开关（1101/3，2026-10-17 抓包破解） -->
    <div v-show="tab === 'gps'" class="pane" role="tabpanel" aria-label="GPS 定位">
      <GpsPanel
        :device="topic('device')"
        :control="control"
        :send-command="sendCommand"
      />
    </div>

    <div v-show="tab === 'motion'" class="pane" role="tabpanel" aria-label="运动控制">
      <div class="risk-warn">
        <span class="risk-warn-icon">⚠</span>
        <div>
          运动控制为<b>写方向</b>通道：下发的轴指令会直接驱动机器人。请确认周围人员已撤离、
          机器人已站立且处于空旷场地，异常时优先点「软急停」。
          <br />切到其他标签时摇杆会<b>立即自动零位停止</b>（不等停更超时）；
          <b>定时移动会在后台继续跑到点</b>（顶部黄条与标签上的倒计时实时可见）。
        </div>
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
        :control-owner="controlOwner"
        :is-control-owner="isControlOwner"
        :watchdog="watchdog"
        :motion="topic('motion')"
        :basic="topic('basic')"
        :device="topic('device')"
        :active="tab === 'motion'"
      />
    </div>

    <!-- 机器人设置：补光灯 / 首启回零 / 休眠 / WiFi 热点。
         同样用 v-show —— 它需要 2Hz 设备帧里的补光灯状态，卸载会丢数据源。 -->
    <div v-show="tab === 'config'" class="pane" role="tabpanel" aria-label="机器人设置">
      <div class="risk-warn">
        <span class="risk-warn-icon">⚠</span>
        <div>
          本页<b>会改变整车行为与网络配置</b>：
          「立即休眠」会让机器人趴下并断电；改 WiFi 热点会让已连设备掉线。
          改热点不会动上行链路（我们 SSH 的通路），但两者共用一块射频，脚本会自动复查并在失败时回滚。
        </div>
      </div>
      <RobotConfigPanel
        :control="control"
        :device="topic('device')"
        :is-control-owner="isControlOwner"
      />
    </div>

    <!-- 指令报文记录（全局）：任何标签页发出的指令都能就地看到响应。
         默认收起，只占一行；展开后才轮询后端。 -->
    <PacketLogPanel />

    <!-- 全局二次确认弹窗（替代 window.confirm） -->
    <ConfirmDialog />
  </div>
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
import ConfirmDialog from './components/ConfirmDialog.vue'
import { useRobotState } from './composables/useRobotState.js'

const s = useRobotState()
const {
  snapshot, topics, connected, staleTopics, sinceSeconds, control, watchdog,
  topic, isStale, sendCommand, sendAxis, sendTimedAxis, stopAxis, estop, clearEstop,
  enableControl, disableControl, renewLease, refreshControl, sendHeartbeat,
  // 控制权归属（多操作员互斥）：**必须解构到顶层**——composable 返回的是普通
  // 对象，不解构拿到的是 Ref、恒为真，会让"非 owner 置灰"彻底失效（ADR-020）。
  controlOwner, isControlOwner
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

/** 暂停按钮的悬停说明：把"会发生什么"讲清楚，避免误当成"断开连接" */
const hbPauseTip = computed(() => (hbConfirming.value
  ? '再点一次即暂停：本页将不再收到机器人状态，控制指令除软急停外均被服务端拒绝'
  : '暂停后本页不再接收机器人状态（非故障）；恢复前驱动类指令会被服务端拒绝'))

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
/* ---------------------------------------------------- 顶栏 */
.app-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  margin-bottom: var(--sp-3);
  background: linear-gradient(180deg, var(--panel) 0%, var(--bg) 160%);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: var(--sh-1);
}

.app-brand { display: flex; align-items: center; gap: var(--sp-3); }

.app-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  font-size: var(--fs-13);
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid rgba(56, 189, 248, 0.35);
  border-radius: var(--r-md);
}

.app-brand-text { min-width: 0; }

.app-title {
  margin: 0;
  font-size: var(--fs-17);
  font-weight: 600;
  color: var(--text-strong);
  line-height: 1.3;
}

.app-subtitle {
  margin: 2px 0 0;
  font-size: var(--fs-12);
  color: var(--muted);
}

.app-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2) var(--sp-3);
}

.meta-item {
  display: inline-flex;
  align-items: baseline;
  gap: var(--sp-2);
  font-size: var(--fs-12);
  cursor: help;
}

.meta-label { color: var(--muted); }

.meta-value {
  font-size: var(--fs-13);
  font-weight: 600;
  color: var(--text);
}

@media (max-width: 720px) {
  .app-header { align-items: flex-start; }
  .app-meta { width: 100%; }
}

/* ---------------------------------------------------- 提示条 */
.banner-stack { display: flex; flex-direction: column; gap: var(--sp-2); }

.banner {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-13);
  font-weight: 500;
  line-height: 1.6;
  color: #fff;
  background: var(--danger-solid);
  border-radius: var(--r-md);
  box-shadow: var(--sh-1);
}

.banner-icon { font-size: var(--fs-15); flex: 0 0 auto; }
.banner-text { flex: 1 1 auto; min-width: 0; }
.banner b { font-weight: 700; }

/* 语义区分：红=链路故障 / 琥珀=部分停更 / 深琥珀=运动进行中或主动暂停 */
.banner.is-danger { background: var(--danger-solid); }
.banner.is-warn { background: var(--warn-solid); }
.banner.is-motion { background: var(--warn-solid); }

.banner .btn-sm {
  flex: 0 0 auto;
  color: var(--text-strong);
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.45);
}
.banner .btn-sm:hover:not(:disabled) { background: rgba(255, 255, 255, 0.24); }

.banner-stack:not(:empty) { margin-bottom: var(--sp-3); }

/* ---------------------------------------------------- 标签页 */
.tabs {
  display: flex;
  gap: var(--sp-1);
  margin-bottom: var(--sp-3);
  padding: var(--sp-1);
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  /* 窄屏可横向滑动，不挤压标签文字 */
  overflow-x: auto;
  scrollbar-width: thin;
}

.tab {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
  font-size: var(--fs-13);
  font-weight: 600;
  font-family: inherit;
  color: var(--muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
}

.tab:hover:not(.active) {
  color: var(--text);
  background: var(--panel-2);
  border-color: var(--line);
}

.tab.active {
  color: #fff;
  background: var(--accent-strong);
  border-color: var(--accent-strong);
}

/* 运动控制 / 机器人设置是写方向入口：激活态用警示色而非主色（与 lite3 monitor 一致） */
.tab.risk.active {
  background: var(--warn-solid);
  border-color: var(--warn-solid);
}

.risk-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--danger);
  box-shadow: 0 0 0 3px var(--danger-soft);
}

/* 定时移动进行中：标签上的倒计时角标 */
.tab-badge {
  padding: 1px 7px;
  font-size: var(--fs-11);
  font-variant-numeric: tabular-nums;
  color: #fff;
  background: var(--danger);
  border-radius: var(--r-pill);
}

/* ---------------------------------------------------- 写方向页顶部警示 */
/* 独占整行的规则已收敛到全局 style.css 的 .pane（flex-basis:100%） */

.risk-warn {
  display: flex;
  gap: var(--sp-2);
  padding: var(--sp-3);
  margin-bottom: 0;
  font-size: var(--fs-13);
  line-height: 1.7;
  color: var(--warn-text);
  background: var(--warn-soft);
  border: 1px solid var(--warn-line);
  border-radius: var(--r-md);
}

.risk-warn-icon { flex: 0 0 auto; font-size: var(--fs-15); }
.risk-warn b { color: var(--warn-text-strong); }
</style>
