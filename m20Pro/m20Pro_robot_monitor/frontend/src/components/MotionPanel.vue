<template>
  <!-- span-all：本页只有这一个面板，占满整行；内部再分双栏，避免右侧大片留白 -->
  <div class="panel span-all">
    <h3>
      运动控制
      <small>（控制分层 L0/L1 · 当前 {{ ctrl.enabled ? 'L1 可操控' : 'L0 只监' }}）</small>
      <span class="spacer" />
      <span class="pill" :class="ctrl.estop ? 'pill-bad' : (ctrl.enabled ? 'pill-ok' : 'pill-muted')">
        <span class="status-dot" :class="ctrl.estop ? 'bad pulse' : (ctrl.enabled ? 'ok' : 'off')" />
        {{ ctrl.estop ? '急停已锁定' : (ctrl.enabled ? '控制已开启' : '控制未开启') }}
      </span>
      <!-- 多操作员互斥：被别的终端占着控制权时，明确告知是谁、本终端只读 -->
      <span v-if="heldByOther" class="pill pill-warn">控制权在「{{ ownerText }}」手中，本终端只读</span>
    </h3>

    <!-- ============================================ 当前状态一览（2026-10-20 加）
         动机：操作员问得最多的是"这台狗现在什么状态"—— 站着还是趴着？什么步态？
         灯亮没亮？以前这些散在四个分区里，要逐个展开看。
         这里做成**常驻的徽标墙**，一眼扫完；字段全部来自 WS 快照（basic / device
         topic）里**车侧已给出**的值与 *_label，前端不做二次臆造判定。
         只做展示，不提供操作 —— 要改就进下面各分区。 -->
    <section class="msec mstate">
      <div class="msec-head">
        <span class="block-title">当前状态</span>
        <span class="hint">车侧实时上报（约 100ms 一帧）· 与「基础状态」页同源，仅展示、不可在此修改</span>
      </div>
      <div class="mstate-grid">
        <div
          v-for="it in stateItems"
          :key="it.label"
          class="mstate-item"
          :title="it.tip"
        >
          <span class="mstate-k">{{ it.label }}</span>
          <span class="pill" :class="it.cls">
            <span class="status-dot" :class="it.dot" />
            <span class="mstate-v">{{ it.text }}</span>
          </span>
        </div>
      </div>
    </section>

    <!-- 四个分区排成**两列独立流**（.mgrid/.mgcol 见全局 style.css）：
         左列 = 控制权与整机指令 + 车侧反馈（162 + 464）
         右列 = 虚拟摇杆 + 定时移动      （398 + 243）
         实测两列总高 638 / 653（差 15px）—— 用 grid 按行排布会出现 302px/335px
         的行内大空洞（2026-10-20 实测），故改用两个纵向流各自堆叠。
         窄屏（≤980px）塌成单列，DOM 顺序不变。 -->
    <div class="mgrid">
      <div class="mgcol">

    <!-- ============================================ 控制权与整机指令 -->
    <CollapsibleSection
      title="控制权与整机指令"
      hint="未取得控制权时，下面除软急停外的按钮都会置灰"
      store-key="motion-cmd"
    >
      <div class="btn-row">
        <!-- 开启控制：写方向总闸，开启前二次确认 -->
        <button
          v-if="!ctrl.enabled"
          class="btn-primary"
          :class="{ 'btn-loading': ctrlBusy === 'enable' }"
          :disabled="!!ctrlBusy"
          title="开启后本终端才能下发运动指令（会占用全局控制权）"
          @click="onEnable(false)"
        >{{ ctrlBusy === 'enable' ? '开启中…' : '开启控制' }}</button>
        <template v-else>
          <button
            v-if="isControlOwner"
            :class="{ 'btn-loading': ctrlBusy === 'disable' }"
            :disabled="!!ctrlBusy"
            title="释放本终端的控制权，回到 L0 只监（其他终端随后可申请）"
            @click="onDisable"
          >{{ ctrlBusy === 'disable' ? '释放中…' : '释放控制权' }}</button>
          <button
            v-else
            class="btn-danger"
            :class="{ 'btn-loading': ctrlBusy === 'enable' }"
            :disabled="!!ctrlBusy"
            title="从其他终端手中接管控制权（对方会被置为只读）"
            @click="onEnable(true)"
          >{{ ctrlBusy === 'enable' ? '接管中…' : '接管控制权' }}</button>
        </template>

        <!-- 软急停：安全手段优先于开关，L0 下也可用 -->
        <button
          class="btn-danger"
          :class="{ 'btn-loading': cmdBusy === 'estop' }"
          :disabled="!!cmdBusy"
          title="立即进入阻尼状态并停止运动（任何情况下都可用）"
          @click="onEstop"
        >{{ cmdBusy === 'estop' ? '下发中…' : '软急停' }}</button>
        <button
          v-if="ctrl.estop"
          :class="{ 'btn-loading': cmdBusy === 'clear_estop' }"
          :disabled="!!cmdBusy"
          title="解除急停锁定，恢复指令通道（解除后不会自动运动）"
          @click="onClearEstop"
        >{{ cmdBusy === 'clear_estop' ? '解除中…' : '解除急停锁定' }}</button>

        <span class="btn-sep" />

        <button
          :disabled="!canDrive || !!cmdBusy"
          :class="{ 'btn-loading': cmdBusy === 'stand_up' }"
          :title="disabledTip || '让机器人从趴下 / 阻尼态起立'"
          @click="onStand"
        >{{ cmdBusy === 'stand_up' ? '起立中…' : '站立' }}</button>
        <button
          :disabled="!canDrive || !!cmdBusy"
          :class="{ 'btn-loading': cmdBusy === 'lie_down' }"
          :title="disabledTip || '让机器人降低机身趴下'"
          @click="onLieDown"
        >{{ cmdBusy === 'lie_down' ? '趴下中…' : '趴下' }}</button>
        <button
          :disabled="!canDrive || !!cmdBusy"
          :class="{ 'btn-loading': cmdBusy === 'wake_up' }"
          :title="wakeTip"
          @click="onWake"
        >{{ cmdBusy === 'wake_up' ? '唤醒中…' : '唤醒整车' }}</button>
      </div>

      <div class="grid">
        <div class="kv"><span>租约剩余</span><span>{{ (ctrl.lease_remaining ?? 0).toFixed(1) }} s</span></div>
        <div class="kv"><span>急停锁定</span><span>{{ ctrl.estop ? '是' : '否' }}</span></div>
        <div class="kv"><span>已发指令</span><span>{{ ctrl.sent_packets ?? 0 }}</span></div>
        <div class="kv"><span>被拒指令</span><span>{{ ctrl.rejected_packets ?? 0 }}</span></div>
        <div class="kv"><span>控制权</span><span>{{ ownerText }}</span></div>
      </div>
    </CollapsibleSection>

    <!-- ============================================ 车侧反馈 -->
    <CollapsibleSection
      title="车侧反馈"
      hint="推了摇杆车不动时，先看这里"
      store-key="motion-feedback"
    >
      <div class="row" style="margin-bottom: var(--sp-3)">
        <!-- 步态：下拉框 → 按钮组。
             高亮的就是**当前选择的步态**；右侧「当前生效」是车侧回读的真实值，
             两者在下发后的 1~2s 内可能不一致（车侧确认后收敛）。 -->
        <SegmentedControl
          label="步态"
          :options="GAIT_OPTIONS"
          :value="gait"
          :disabled="!canDrive"
          :busy="cmdBusy === 'gait'"
          @set="setGait"
        />
        <span class="hint">当前生效：{{ gaitLabel }}</span>
      </div>

      <div class="grid" style="margin-bottom: var(--sp-2)">
        <div class="kv"><span>运动状态</span><span>{{ motionLabel }}</span></div>
        <div class="kv"><span>实际 前后 X</span><span>{{ n3(motion.linear_x) }} m/s</span></div>
        <div class="kv"><span>实际 左右 Y</span><span>{{ n3(motion.linear_y) }} m/s</span></div>
        <div class="kv"><span>实际 转向 ω</span><span>{{ n3(motion.omega_z) }} rad/s</span></div>
        <div class="kv"><span>关节回零</span><span>{{ zeroLabel }}</span></div>
        <div class="kv"><span>雷达供电 前/后</span><span>{{ lidarLabel }}</span></div>
      </div>

      <!-- 雷达供电开关（1101/3，2026-10-17 抓包破解）：
           可单独控制前/后雷达。**站立/RL 运动中关闭会被服务端拒绝**——
           雷达是运控的平衡参考输入，这是有意为之的保守策略（厂商 App 不拦，我们拦）。 -->
      <div class="devbar">
        <span class="devbar-label">雷达供电</span>
        <DeviceToggle
          label="前雷达"
          :value="props.device?.lidar_front ?? null"
          :disabled="!canDrive"
          :busy="!!devBusy"
          @set="(v) => setLidar('Front', v)"
        />
        <DeviceToggle
          label="后雷达"
          :value="props.device?.lidar_back ?? null"
          :disabled="!canDrive"
          :busy="!!devBusy"
          @set="(v) => setLidar('Back', v)"
        />
        <span v-if="devMsg" class="hint">{{ devMsg }}</span>
        <span v-if="devErr" class="hint err">{{ devErr }}</span>
      </div>
      <!-- 指向"默认行为"配置入口：这里的开关管"现在"，默认关闭策略管"以后" -->
      <div class="hint" style="margin-top: var(--sp-2)">
        想让雷达在<b>开机 / 唤醒后自动保持关闭</b>？到「机器人设置」页打开「雷达默认关闭」
        （会影响建图 / 定位 / 导航，页内有完整影响说明）。
      </div>

      <!-- 其他设备供电（同一条 1101/3，换 Items 键即可）：
           键名与语义全部经车侧日志逐条实证，见 patrol_codec.DEVICE_SWITCH_SPEC -->
      <div class="devbar" style="margin-top: var(--sp-2)">
        <span class="devbar-label">其他设备供电</span>
        <DeviceToggle
          v-for="d in OTHER_DEVICES"
          :key="d.key"
          :label="d.label"
          :value="props.device?.[d.field] ?? null"
          :disabled="!canDrive"
          :busy="!!devBusy"
          @set="(v) => setFlag(d.key, v)"
        />
        <!-- 风扇是 0~100 而非开关：同样用「开/关」两个选项，转速作为副标注 -->
        <DeviceToggle
          label="风扇"
          :value="props.device?.fan_speed ?? null"
          :hint="fanHint"
          :disabled="!canDrive"
          :busy="!!devBusy"
          @set="setFan"
        />
      </div>

      <div v-if="!motionReady" class="warn-box" style="margin-top: var(--sp-2)">
        ⚠ 当前「{{ motionLabel }}」—— 轴指令<b>只在「站立 / RL 控制」下生效</b>，请先点「站立」
      </div>
      <!-- 开机阻尼态：车侧默认 autoResetJointsZero=true，点「站立」时运控会先回零再起立 -->
      <div v-if="isBootDamping" class="warn-box" style="margin-top: var(--sp-2)">
        ⚠ 当前是「开机阻尼」态 —— 车侧默认开启<b>自动回零</b>
        （<code>autoResetJointsZero = true</code>），点「站立」后运控会<b>先完成关节回零再起立</b>，
        所以首次站立比后续站立慢、且中途不要干预。
      </div>
      <template v-else>
        <div v-if="joyLateralWarn" class="warn-box" style="margin-top: var(--sp-2)">⚠ {{ joyLateralWarn }}</div>
        <div class="hint" style="margin-top: var(--sp-2)">
          诊断：发了横移却不动时，看「实际 左右 Y」—— 恒为 0 = 车侧没执行（步态不支持）；
          有值但机身不挪 = 轮足侧向打滑
        </div>
      </template>
    </CollapsibleSection>

      </div><!-- /.mgcol（左列） -->
      <div class="mgcol">

    <!-- ============================================ 速度控制（虚拟摇杆） -->
    <!-- 折叠时必须先松手：摇杆用了 setPointerCapture，元素被移除后 pointerup
         不一定送达，看门狗可能继续喂轴 → 车在看不见的面板后面继续走 -->
    <CollapsibleSection
      title="速度控制（虚拟摇杆）"
      store-key="motion-joystick"
      @update:open="onJoystickSectionToggle"
    >
      <div class="joy-head">
        <span class="block-title">速度控制（虚拟摇杆）</span>
        <!-- 摇杆水平轴模式：与步态 / 方向 / 通道同一套分段按钮，高亮 = 当前模式。
             这是纯前端状态（只改摇杆映射，不下发给车侧）。 -->
        <SegmentedControl
          aria-label="摇杆水平轴模式"
          :options="JOY_MODE_OPTIONS"
          :value="joyMode"
          @set="setJoyMode"
        />
      </div>

      <div
        ref="joyEl"
        class="joy"
        :class="{ disabled: !ctrl.enabled || ctrl.estop }"
        @pointerdown="onJoyDown"
        @pointermove="onJoyMove"
        @pointerup="onJoyUp"
        @pointercancel="onJoyUp"
      >
        <span class="joy-axis joy-axis-top">前</span>
        <span class="joy-axis joy-axis-bottom">后</span>
        <span class="joy-axis joy-axis-left">{{ joyMode === 'xy' ? '左移' : '左转' }}</span>
        <span class="joy-axis joy-axis-right">{{ joyMode === 'xy' ? '右移' : '右转' }}</span>
        <div class="joy-knob" :class="{ active: joyActive }" :style="knobStyle" />
        <!-- 不可用时给明确原因，而不是让人以为是控件坏了 -->
        <div v-if="!ctrl.enabled || ctrl.estop" class="joy-mask">
          {{ ctrl.estop ? '急停已锁定，请先「解除急停锁定」' : '请先在上方「开启控制」' }}
        </div>
      </div>

      <div class="joy-read">
        下发轴值 前后 <b class="num">{{ readout.x }}</b> ·
        {{ joyMode === 'xy' ? '左右' : '旋转' }} <b class="num">{{ readout.h }}</b>
        <span class="dim">（拖动中约 16Hz 持续下发 · 松手 → 零位停止，不软急停）</span>
      </div>

      <div class="warn-box joy-tip">
        ⚠ 平移/转向存在车侧起动阈值：推杆幅度太小可能原地不动（前后方向阈值较低）；
        <b>左右平移 / 转向未经实车标定</b>，请小幅慢试。
        松手 / 断流只会「零位停」，绝不自动软急停；急停请点上方「软急停」。
      </div>

      <div class="speed-line">
        <label for="speed-limit">速度上限</label>
        <input
          id="speed-limit"
          type="number"
          min="0.05"
          max="0.4"
          step="0.01"
          v-model.number="speed"
          :class="{ 'is-invalid': !!speedError }"
          @change="normalizeSpeed"
        />
        <span v-if="speedError" class="field-msg err">{{ speedError }}</span>
        <span v-else class="hint">0.05 ~ 0.40（默认 0.25 ≈ 实测舒适档；摇杆满舵 = 所填数值）</span>
      </div>
    </CollapsibleSection>

    <!-- ============================================ 定时移动 -->
    <!-- 定时移动（2026-10-16 加）：选方向 + 速度 + 秒数，后端计时到点自动停。
         计时放后端：浏览器定时器会被节流（切后台/省电），前端计时停不住车。
         「执行中」徽标放在折叠头部 —— 折叠后也要看得见车还在动。 -->
    <CollapsibleSection
      title="定时移动（方向 · 速度 · 秒数）"
      store-key="motion-timed"
      default-open
    >
      <template #badge>
        <span class="pill" :class="timedActive ? 'pill-ok' : 'pill-muted'">
          <span class="status-dot" :class="timedActive ? 'ok pulse' : 'off'" />
          <template v-if="timedActive">
            执行中 · 剩余 {{ timedRemaining.toFixed(1) }} s / 共 {{ timedTotal.toFixed(1) }} s
          </template>
          <template v-else>空闲</template>
        </span>
      </template>

      <div class="timed-row">
        <!-- 方向：下拉框 → 按钮组（执行中禁用改方向，避免中途换向） -->
        <SegmentedControl
          label="方向"
          :options="timedDirOptions"
          :value="timedDir"
          :disabled="timedActive"
          @set="setTimedDir"
        />
        <span class="field">
          <label class="field-label" for="timed-speed">速度</label>
          <input
            id="timed-speed"
            type="number"
            min="0.05"
            max="0.4"
            step="0.01"
            v-model.number="timedSpeed"
            :disabled="timedActive"
            @change="clampTimedSpeed"
          />
        </span>
        <span class="field">
          <label class="field-label" for="timed-sec">秒数</label>
          <input
            id="timed-sec"
            type="number"
            min="0.5"
            max="30"
            step="0.5"
            v-model.number="timedSeconds"
            :disabled="timedActive"
            @change="clampTimedSeconds"
          />
        </span>
        <!-- 通道：下拉框 → 按钮组 -->
        <SegmentedControl
          label="通道"
          :options="timedChannelOptions"
          :value="timedChannel"
          :disabled="timedActive"
          @set="setTimedChannel"
        />
        <button
          v-if="!timedActive"
          class="btn-primary"
          :class="{ 'btn-loading': timedStarting }"
          :disabled="!ctrl.enabled || ctrl.estop || timedStarting"
          :title="disabledTip || '按上面的方向 / 速度 / 秒数开始移动（到点自动零位停止）'"
          @click="startTimed"
        >{{ timedStarting ? '下发中…' : '开始定时移动' }}</button>
        <button
          v-else
          class="btn-danger"
          :class="{ 'btn-loading': timedStopping }"
          :disabled="timedStopping"
          title="立即零位停止（不触发软急停）"
          @click="abortTimed"
        >{{ timedStopping ? '中止中…' : '中止移动' }}</button>
      </div>

      <div v-if="timedWarn" class="warn-box" style="margin-top: var(--sp-2)">⚠ {{ timedWarn }}</div>

      <div class="note timed-tip">
        到点自动「零位停止」（不软急停），计时在后端完成 —— 浏览器切后台也按时停。<br />
        横移（左移 / 右移）需先把步态切到「平地（敏捷）0x3002」：2026-10-16 实测，
        0x1001 基础（标准）下 Y 指令只原地调姿态、不位移（steer / real 两条通道一致）。
        「通道」选择保留作排查工具。
      </div>
    </CollapsibleSection>

      </div><!-- /.mgcol（右列） -->
    </div><!-- /.mgrid -->

    <div v-if="lastResult" class="last-result">
      <span class="pill pill-info">最近结果</span>{{ lastResult }}
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import CollapsibleSection from './CollapsibleSection.vue'
import DeviceToggle from './DeviceToggle.vue'
import SegmentedControl from './SegmentedControl.vue'
import { useDeviceSwitch } from '../composables/useDeviceSwitch.js'
import { askConfirm } from '../composables/useConfirm.js'

const props = defineProps({
  control: { type: Object, default: () => ({}) },
  sendCommand: { type: Function, required: true },
  sendAxis: { type: Function, required: true },
  sendTimedAxis: { type: Function, required: true },
  stopAxis: { type: Function, required: true },
  estop: { type: Function, required: true },
  clearEstop: { type: Function, required: true },
  enableControl: { type: Function, required: true },
  disableControl: { type: Function, required: true },
  renewLease: { type: Function, default: null },
  //: 控制权归属（多操作员互斥，2026-10-19 加）
  //  controlOwner：后端给的占用者信息 { held, session, label, age_s, idle_s }
  //  isControlOwner：本终端是否就是 owner（决定按钮是"释放"还是"接管"）
  controlOwner: { type: Object, default: () => ({}) },
  isControlOwner: { type: Boolean, default: false },
  refreshControl: { type: Function, default: null },
  //: 本面板是否可见（App.vue 标签页传入）。**切走即松手**：摇杆用了
  //  setPointerCapture，多指触屏下"一指按摇杆、一指切标签"会让捕获中的
  //  pointermove 继续喂看门狗——车会在看不见的标签后面继续走。
  active: { type: Boolean, default: true },
  //: 看门狗状态（定时移动倒计时来源；2026-10-16 加）
  watchdog: { type: Object, default: () => ({}) },
  // 车侧状态（诊断用）：实际速度反馈 + 当前步态 + 运动状态
  motion: { type: Object, default: () => ({}) },
  basic: { type: Object, default: () => ({}) },
  // 设备状态（2026-10-17 加）：提供 DevEnable 分设备供电使能
  device: { type: Object, default: () => ({}) }
})

const ctrl = ref(props.control)
watch(() => props.control, (v) => { ctrl.value = v || {} }, { deep: true })

// ---- 按钮加载态（仅展示用）：避免重复点击造成重复下发 ----
const cmdBusy = ref('')      // 正在下发的整机指令
const ctrlBusy = ref('')     // 正在申请/释放控制权
const timedStarting = ref(false)
const timedStopping = ref(false)
const lastResult = ref('')

/** 指令的中文名（用于提示文案，避免把 stand_up 这类内部名直接甩给用户） */
const CMD_LABEL = {
  stand_up: '站立',
  lie_down: '趴下',
  wake_up: '唤醒整车',
  gait: '步态切换',
  estop: '软急停',
  clear_estop: '解除急停锁定'
}

// ---- 车侧实际速度反馈（2026-10-16 加）----
// 用途：推摇杆却不动时，用它判别"指令被忽略"还是"车在动但看不出来"：
//   · 发了 y=0.4 但 linear_y 恒为 0  → 车侧没执行横移（步态/模式不支持）
//   · linear_y 有非零值但机身位移极小 → 轮足侧向打滑，属能力所限
const n3 = (v) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(3))
const GAIT_LABEL = {
  4097: '0x1001 基础（标准）',
  4099: '0x1003 楼梯（标准）',
  12290: '0x3002 平地（敏捷）',
  12291: '0x3003 楼梯（敏捷）',
}
const gaitLabel = computed(() => {
  const b = props.basic || {}
  // 优先用车侧下发的标签（与「基础状态」页同源，避免两处语义漂移）；
  // 车侧没给标签时（老固件 / mock）才退回本地映射表兜底。
  if (b.gait_label) return b.gait_label
  const g = b.gait
  if (!g) return '—'
  return GAIT_LABEL[g] || `0x${Number(g).toString(16)}`
})

// ---- 横移步态提示（2026-10-16 真机对照实验结论）----
// 实测：0x1001 基础（标准）步态下 Y 指令只原地调姿态、不位移，steer / real 两条通道
// 表现一致；切 0x3002 平地（敏捷）后横移生效（vy 抬升 2× 底噪 + 站高 0.574→0.46）。
// ⇒ 横移能力由**步态**决定，与通道无关。只提示、不拦截。
function lateralHint (g) {
  if (g === 0x1001) {
    return '「基础（标准）0x1001」不支持横移（2026-10-16 实测）—— Y 指令只会原地调整姿态、'
      + '不位移，请先切「平地（敏捷）0x3002」'
  }
  if (g === 0x1003) {
    return '「楼梯（标准）0x1003」与基础同系、横移未实测 —— 若原地不动请切「平地（敏捷）0x3002」'
  }
  return ''
}
const MOTION_LABEL = { 0: '空闲', 1: '站立', 2: '软急停阻尼', 3: '开机阻尼', 4: '趴下', 17: 'RL 控制' }
const motionLabel = computed(() => {
  const m = props.basic?.motion_state
  if (m == null) return '—'
  // 同样优先车侧标签（motion_state_label），本地表只作兜底
  return props.basic?.motion_state_label || MOTION_LABEL[m] || `未知(${m})`
})
const motionReady = computed(() => [1, 17].includes(props.basic?.motion_state))

// ---- 当前状态一览（2026-10-20 加）----
// 原则：**只展示车侧已经给出的值**，不在前端另造一套判定。
//   · 文本一律用后端下发的 *_label（motion_state_label / gait_label / sleep_label …）；
//   · 只有"着色"是前端做的映射，且映射规则与 RobotStatus.vue 的运动状态着色保持一致；
//   · 补光灯取设备帧 Led.Fill 的扁平字段 fill_front / fill_back（1101/2 下发后车侧回翻）。
// 0/1 之外的取值（null = 尚未收到该字段）一律显示「—」并置灰，不猜。
const POSTURE_TONE = {
  0: { cls: 'pill-muted', dot: 'off' },  // 空闲
  1: { cls: 'pill-ok', dot: 'ok' },      // 站立
  2: { cls: 'pill-warn', dot: 'warn' },  // 软急停阻尼
  3: { cls: 'pill-warn', dot: 'warn' },  // 开机阻尼
  4: { cls: 'pill-muted', dot: 'off' },  // 趴下
  17: { cls: 'pill-ok', dot: 'ok' }      // RL 控制
}
/** 开关类字段（补光灯等）的着色：1=开(绿) / 0=关(灰) / 未知=灰 */
function onoffTone (v) {
  if (v == null) return { cls: 'pill-muted', dot: 'off' }
  return Number(v) ? { cls: 'pill-ok', dot: 'ok' } : { cls: 'pill-muted', dot: 'off' }
}

const stateItems = computed(() => {
  const b = props.basic || {}
  const d = props.device || {}
  const posture = POSTURE_TONE[b.motion_state] || { cls: 'pill-muted', dot: 'off' }
  return [
    {
      label: '姿态',
      text: b.motion_state_label || '—',
      ...posture,
      tip: '车侧运动状态（motion_state）。站立 / RL 控制下轴指令才生效；趴下与阻尼态只监不可控'
    },
    {
      label: '步态（当前生效）',
      text: gaitLabel.value,
      cls: 'pill-info', dot: 'info',
      tip: '车侧回读的当前步态。与上方「步态」按钮的选择值在切换后 1~2s 内可能不一致（等车侧确认）'
    },
    {
      label: '前补光灯',
      text: d.fill_front == null ? '—' : (Number(d.fill_front) ? '已亮起' : '已熄灭'),
      ...onoffTone(d.fill_front),
      tip: '前照明探照灯：1101/2 下发，设备帧 Led.Fill.Front 回读（可在「机器人设置」页切换）'
    },
    {
      label: '后补光灯',
      text: d.fill_back == null ? '—' : (Number(d.fill_back) ? '已亮起' : '已熄灭'),
      ...onoffTone(d.fill_back),
      tip: '后照明探照灯：1101/2 下发，设备帧 Led.Fill.Back 回读（可在「机器人设置」页切换）'
    },
    {
      label: '硬急停（HES）',
      text: b.hes === 1 ? '已触发' : (b.hes == null ? '—' : '未触发'),
      cls: b.hes === 1 ? 'pill-bad' : 'pill-ok',
      dot: b.hes === 1 ? 'bad pulse' : 'ok',
      tip: '车体硬件急停按钮状态，与网页上的「软急停」相互独立；触发后需人工到车体解除'
    },
    {
      label: '整车休眠',
      text: b.sleep_label || '—',
      cls: b.sleep ? 'pill-warn' : 'pill-muted',
      dot: b.sleep ? 'warn' : 'off',
      tip: '整车休眠状态（1101/6 唤醒）。休眠时相机 / 雷达 / GPS / 关节供电会被关闭'
    },
    {
      label: '充电状态',
      text: b.charge_label || '—',
      cls: b.charge ? 'pill-ok' : 'pill-muted',
      dot: b.charge ? 'ok' : 'off',
      tip: '车侧上报的充电状态（charge）'
    },
    {
      label: '控制权',
      text: ownerText.value,
      cls: heldByOther.value ? 'pill-warn' : (ctrl.value.enabled ? 'pill-ok' : 'pill-muted'),
      dot: heldByOther.value ? 'warn' : (ctrl.value.enabled ? 'ok' : 'off'),
      tip: '全局控制闸当前归属：同一时刻只有一个终端能下发运动指令'
    }
  ]
})

// ---- 关节回零（2026-10-17 取证）----
// 车侧 basic_server.toml 默认 `autoResetJointsZero = true`，BasicStatus 上报带
// `ResetJointsZero` 字段。值域未见官方文档，故标签由后端保守给出、前端不臆造。
const zeroLabel = computed(() => props.basic?.reset_joints_zero_label || '—')
// 开机阻尼态（MotionParam=3）：此时点「站立」，运控会先跑 ZeroCalibrationState 回零再起立
const isBootDamping = computed(() => props.basic?.motion_state === 3)

// ---- 设备供电开关（1101/3，2026-10-17 抓包破解）----
// 此前判断"协议未公开单独开/关雷达"是**错的** —— 抓包拿到 1101/3，
// Items 键名决定目标设备（Lidar/Video/GPS/...），已逐键经车侧日志实证。
// ⚠️ 必须解构到顶层：Vue 3 模板只对**顶层** setup 绑定做 ref 解包，
// 写成 `dev.busy` 拿到的是 Ref 对象本身（恒真）→ `:disabled` 永远为真。
// 这正是 2026-10-17 用户反馈"供电开关按钮按不了"的根因。
const { busy: devBusy, msg: devMsg, err: devErr,
        apply: devApply, setPair } = useDeviceSwitch(props)
const onoff = (v) => (v == null ? '—' : (Number(v) ? '开' : '关'))
const lidarLabel = computed(() => {
  const f = onoff(props.device?.lidar_front)
  const b = onoff(props.device?.lidar_back)
  return (f === '—' && b === '—') ? '—' : `${f} / ${b}`
})
const lidarVal = (side) => (side === 'Front' ? props.device?.lidar_front : props.device?.lidar_back)
const lidarOther = (side) => (side === 'Front' ? props.device?.lidar_back : props.device?.lidar_front)
function setLidar (side, v) {
  // 1101/3 是**整键覆写**，必须把另一路的当前值一起带上，
  // 否则只改一路会把没点的那路默认成 0（= 顺带关掉）。
  setPair('Lidar', side, v, lidarOther(side))
}

// 其他单路设备（键名/标签经车侧日志逐条实证，见 patrol_codec.DEVICE_SWITCH_SPEC）
const OTHER_DEVICES = [
  { key: 'LedHost', field: 'led_host', label: '主机电源指示灯' },
  { key: 'LedExt', field: 'led_ext', label: '外部负载指示灯' },
  { key: 'LoadPower', field: 'load_power', label: '外部负载供电' },
  { key: 'FP', field: 'fp', label: '对频模块' }
]
function setFlag (key, v) {
  devApply(key, { [key]: v }, '', v === 0)
}

// 风扇：0 与 100 两档（真机只实测过 100；转速语义未见文档，故不做连续滑杆）
async function setFan (v) {
  const next = v ? 100 : 0
  await devApply('FanSpeed', { FanSpeed: next }, '', next === 0)
}

// 风扇转速副标注：带单位词，避免裸数字被误读成温度/错误码
const fanHint = computed(() => {
  const v = props.device?.fan_speed
  return (v === null || v === undefined) ? '' : `转速 ${v}`
})

// 唤醒 = 退出整车休眠（1101/6），会连带恢复相机/雷达/GPS/关节供电 —— 标注清楚避免误解
const wakeTip = computed(() => (ctrl.value.enabled
  ? '退出整车休眠（1101/6）—— 会同时恢复相机 / 雷达 / GPS / 关节供电'
  : disabledTip.value))

/** 步态选项：4 档互斥，按键即切换（原为下拉框，看不到当前值） */
const GAIT_OPTIONS = [
  { value: 0x1001, label: '基础（标准 · 0x1001）',
    tip: '切到「基础（标准）0x1001」：默认平地步态。此步态下横移 Y 只调姿态、不产生位移' },
  { value: 0x1003, label: '楼梯（标准 · 0x1003）',
    tip: '切到「楼梯（标准）0x1003」：标准系上 / 下楼梯用' },
  { value: 0x3002, label: '平地（敏捷 · 0x3002）',
    tip: '切到「平地（敏捷）0x3002」：唯一支持左右横移的步态（站高会从 0.574 降到约 0.46）' },
  { value: 0x3003, label: '楼梯（敏捷 · 0x3003）',
    tip: '切到「楼梯（敏捷）0x3003」：敏捷系上 / 下楼梯用' }
]

/** 摇杆水平轴模式：只改摇杆映射，是纯前端状态，不下发给车侧 */
const JOY_MODE_OPTIONS = [
  { value: 'xy', label: '前后 + 左右平移',
    tip: '摇杆水平轴 = 左右平移（Y）。注意：横移只有「平地（敏捷 · 0x3002）」步态真正生效' },
  { value: 'xyaw', label: '前后 + 转向',
    tip: '摇杆水平轴 = 转向（Yaw）。所有步态都生效' }
]

const gait = ref(0x1001)

// ---- 控制权归属（多操作员互斥，2026-10-19 加）----
// 后端控制闸是全局单例：同一时刻只有一个 owner，非 owner 发驱动指令会被拒
// （409 NOT_OWNER）。所以按钮不只是"没开控制"才置灰，**被别人占着也要置灰**，
// 否则用户点了必被拒、只会以为面板坏了。
const ownerText = computed(() => {
  const o = props.controlOwner
  if (!o || !o.held) return '未占用'
  if (props.isControlOwner) return '本终端'
  return `${o.label || o.session || '其他终端'}（已持有 ${o.age_s ?? 0}s）`
})
/** 控制权已被别的终端占用（本终端只读） */
const heldByOther = computed(
  () => !!(ctrl.value.enabled && props.controlOwner.held && !props.isControlOwner))
/** 本终端当前能否下发驱动指令 */
const canDrive = computed(() => !!(ctrl.value.enabled && props.isControlOwner))
const disabledTip = computed(() => {
  if (!ctrl.value.enabled) return '需先点「开启控制」'
  if (!props.isControlOwner) return `控制权在「${ownerText.value}」手中，本终端只读`
  return ''
})

// ---------------------------------------------------------------- 速度上限
// 摇杆满舵轴值 = 所填数值（2026-10-15 真机实测：
//   0.25 ≈ 0.32 m/s 舒适档 / 0.40 ≈ 0.54 m/s 上限 / ≥0.70 危险）
const SPEED_MIN = 0.05
const SPEED_MAX = 0.4
const SPEED_DEFAULT = 0.25

function loadSpeed () {
  try {
    const v = Number(window.localStorage.getItem('m20.speedLimit'))
    if (isFinite(v) && v >= SPEED_MIN && v <= SPEED_MAX) return v
  } catch (e) { /* localStorage 不可用时回落默认 */ }
  return SPEED_DEFAULT
}

const speed = ref(loadSpeed())
const speedError = computed(() => {
  const v = Number(speed.value)
  if (!Number.isFinite(v)) return '请填写 0.05 ~ 0.40 之间的数值'
  if (v < SPEED_MIN || v > SPEED_MAX) return `超出允许范围 ${SPEED_MIN} ~ ${SPEED_MAX}（提交时会自动夹回边界）`
  return ''
})

function normalizeSpeed () {
  let v = Number(speed.value)
  if (!isFinite(v) || v <= 0) v = SPEED_DEFAULT
  v = Math.min(SPEED_MAX, Math.max(SPEED_MIN, Math.round(v * 100) / 100))
  speed.value = v
  try { window.localStorage.setItem('m20.speedLimit', String(v)) } catch (e) { /* ignore */ }
  return v
}

// ---------------------------------------------------------------- 虚拟摇杆
// 交互参考 lite3 ControlPanel.vue 的"模拟操作摇杆"：指针事件 + 单位圆归一化。
// 与 lite3 的关键差异：m20 后端 20Hz 看门狗要求 ≤250ms 持续 feed，
// 所以拖动期间由定时器（60ms）持续下发 —— 即使指针不动也必须续发；
// 松手时先等所有在途请求落地，再调 stopAxis（避免残余 feed 复位看门狗）。
const JOY_SEND_MS = 60        // 持续 feed 间隔（后端超时 250ms，留 4 倍余量抗 WiFi 丢包）
const JOY_MAX_INFLIGHT = 3    // 允许同时在途的请求数（网络慢时多发增强抗抖动）
const JOY_DEAD_ZONE = 0.08    // 中心死区：8% 行程内归零（防误触）
const JOY_R = 48              // 手柄行程半径（px），与 CSS 中 .joy(140px) / .joy-knob(44px) 配套

const joyEl = ref(null)
const joyActive = ref(false)
const joyMode = ref('xy')                  // 'xy' = 前后+左右平移；'xyaw' = 前后+转向
//: 摇杆「前后 + 左右平移」模式 + 标准系步态 → 提前警示横移不可用
const joyLateralWarn = computed(() => (joyMode.value === 'xy' ? lateralHint(props.basic?.gait) : ''))
const joyVec = ref({ x: 0, h: 0 })         // 归一化 [-1,1]：x 上推为正(前进)；h 左为正
const readout = ref({ x: '0.00', h: '0.00' })
let joyTimer = null
let joyInFlight = 0

const joyHAxis = computed(() => (joyMode.value === 'xy' ? 'y' : 'yaw'))

/** 归一化摇杆值 → 六轴指令值（满舵 = speed；x 正=前进 / y 正=左移 / yaw 正=左转） */
function joyValues () {
  const s = speed.value
  const v = { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 }
  v.x = Math.round(joyVec.value.x * s * 100) / 100
  v[joyHAxis.value] = Math.round(joyVec.value.h * s * 100) / 100
  return v
}

/** 手柄位置由 joyVec 反推 —— 与读数、模式切换双向同步 */
const knobStyle = computed(() => ({
  left: `calc(50% + ${(-joyVec.value.h * JOY_R).toFixed(1)}px)`,
  top: `calc(50% + ${(-joyVec.value.x * JOY_R).toFixed(1)}px)`
}))

function updateReadout () {
  const s = speed.value
  readout.value = {
    x: (joyVec.value.x * s).toFixed(2),
    h: (joyVec.value.h * s).toFixed(2)
  }
}

function setJoyFromPoint (clientX, clientY) {
  const el = joyEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  const r = Math.min(rect.width, rect.height) / 2
  let dx = (clientX - cx) / r
  let dy = (clientY - cy) / r
  const len = Math.hypot(dx, dy)
  if (len > 1) { dx /= len; dy /= len }   // 限制在单位圆内（满舵 = 圆边）
  if (len < JOY_DEAD_ZONE) {              // 中心死区：轻微误触归零
    joyVec.value = { x: 0, h: 0 }
  } else {
    // 屏幕 y 向下为正：上推 = 前进 → x = -dy；右推 = 右移/右转 → h = -dx
    joyVec.value = { x: -dy, h: -dx }
  }
  updateReadout()
}

/** 持续 feed：每 60ms 一发（看门狗 250ms 超时，留 4 倍余量）。
 *  不阻塞发送（最多 3 发在途）—— 网络慢时让多发请求同时在飞，
 *  提高"250ms 内至少一发到达"的概率（2026-10-15 事故教训：宁可多发）。 */
function pushJoy () {
  if (joyInFlight >= JOY_MAX_INFLIGHT) return
  joyInFlight++
  props.sendAxis(joyValues(), true)
    .catch((err) => {
      lastResult.value = '轴指令发送失败：' + (err && err.message ? err.message : err)
    })
    .finally(() => { joyInFlight-- })
}

function startJoyLoop () {
  if (joyTimer) return
  pushJoy()   // 立即首发，不等第一个 60ms tick
  joyTimer = setInterval(pushJoy, JOY_SEND_MS)
}

function stopJoyLoop () {
  if (joyTimer) {
    clearInterval(joyTimer)
    joyTimer = null
  }
}

function sleep (ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function onJoyDown (ev) {
  if (!ctrl.value.enabled || ctrl.value.estop) return
  // 先续约防抖：页面可能刚从后台回来（定时器被浏览器节流、租约已过期），
  // 不先续约的话首推会被租约闸拒发（表现为"推杆没反应"）
  if (props.renewLease) props.renewLease().catch(() => {})
  joyActive.value = true
  ev.currentTarget.setPointerCapture && ev.currentTarget.setPointerCapture(ev.pointerId)
  setJoyFromPoint(ev.clientX, ev.clientY)
  startJoyLoop()
}

function onJoyMove (ev) {
  if (!joyActive.value) return
  setJoyFromPoint(ev.clientX, ev.clientY)
}

/** 松开摇杆的统一收尾：停循环 → 清值 → 等在途落地 → 零位停止。
 *  松手 / 页面切后台都走这里（2026-10-15 二次事故后加固）。 */
async function releaseJoy (msg) {
  if (!joyActive.value) return
  joyActive.value = false
  stopJoyLoop()
  joyVec.value = { x: 0, h: 0 }
  updateReadout()
  // 等所有在途请求落地（最多 800ms）再发 stopAxis —— 否则残余 feed 可能在
  // 暂停之后到达服务端、把看门狗重新激活（松开后车继续走）
  const t0 = Date.now()
  while (joyInFlight > 0 && Date.now() - t0 < 800) await sleep(25)
  try {
    await props.stopAxis()
    lastResult.value = msg || '已松开：零位停止（不触发软急停）'
  } catch (err) {
    lastResult.value = '停止指令下发失败（车侧 150ms 看门狗将自动清零）：'
      + (err && err.message ? err.message : err)
  }
}

function onJoyUp () {
  releaseJoy()
}

// 页面切后台 / 最小化：自动按"松手"处理。
// 防的是：按住摇杆切走 → 浏览器节流定时器 → feed 断流
//（2026-10-15 二次事故的边界情况之一；后端"断流自动软急停"已同步切除）
function onVisibilityChange () {
  if (document.hidden && joyActive.value) {
    releaseJoy('页面切至后台：已自动零位停止')
  }
}

// 折叠摇杆分区：与"松手 / 切标签"同级的收手条件。
// 摇杆用 setPointerCapture 抓住了指针，分区一折叠元素就从 DOM 上消失，
// pointerup 不一定送达 → 看门狗可能继续喂轴，车会在看不见的面板后面继续走。
function onJoystickSectionToggle (open) {
  if (!open && joyActive.value) {
    releaseJoy('折叠摇杆面板：已自动零位停止')
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

// 切到别的标签 = 与"页面切后台"同级的松手条件（见 props.active 注释）：
// 摇杆有 setPointerCapture，隐藏后事件仍可能继续到达，必须显式收手。
watch(() => props.active, (on) => {
  if (!on && joyActive.value) releaseJoy('切换标签：已自动零位停止')
})

/** 切换摇杆水平轴：清掉上一模式遗留值，避免残速 */
function setJoyMode (mode) {
  if (joyMode.value === mode) return
  joyMode.value = mode
  joyVec.value = { x: joyVec.value.x, h: 0 }
  updateReadout()
}

watch(speed, updateReadout)

// ---------------------------------------------------------------- 定时移动（2026-10-16 加）
// 设计要点：计时放**后端**（前端 setInterval 会被浏览器节流，靠它停不住车）。
// 前端只负责：选参数 → 调一次 API → 轮询后端状态显示倒计时；中止 = 调 stopAxis。
// 通道 steer(2/21) / real(2/25)：两通道字段同构、订阅方不同，可做对照排查。
const TIMED_DIRS = {
  forward: { label: '前进', axes: { x: 1 } },
  back: { label: '后退', axes: { x: -1 } },
  left: { label: '左移', axes: { y: 1 } },
  right: { label: '右移', axes: { y: -1 } },
  yaw_left: { label: '左转', axes: { yaw: 1 } },
  yaw_right: { label: '右转', axes: { yaw: -1 } }
}
const TIMED_MIN_S = 0.5
const TIMED_MAX_S = 30

const timedDir = ref('forward')
const timedSpeed = ref(SPEED_DEFAULT)
const timedSeconds = ref(2)
const timedChannel = ref('steer')

/** 方向选项（原下拉框）→ 按钮组，高亮 = 当前选择 */
const timedDirOptions = computed(() =>
  Object.entries(TIMED_DIRS).map(([key, d]) => ({
    value: key,
    label: d.label,
    tip: `方向：${d.label}（按「速度上限」的比例下发，持续指定秒数后自动零位停止）`
  })))

function setTimedDir (v) { timedDir.value = v }
function setTimedChannel (v) { timedChannel.value = v }

/** 通道选项（原下拉框）→ 按钮组；两通道字段同构、订阅方不同，仅用于对照排查 */
const timedChannelOptions = [
  { value: 'steer', label: '主通道 steer（2/21）', tip: '主通道 steer（2/21）：默认使用的运动指令通道' },
  { value: 'real', label: '实时通道 real（2/25）', tip: '实时通道 real（2/25）：字段与 steer 同构，订阅方不同，仅用于对照排查' }
]

const timedActive = computed(() => !!(props.watchdog && props.watchdog.timed_active))
const timedRemaining = computed(() => Number((props.watchdog && props.watchdog.timed_remaining) || 0))
const timedTotal = computed(() => Number((props.watchdog && props.watchdog.timed_total) || 0))

//: 选中方向是否含横移（左移 / 右移）
const timedIsLateral = computed(() => ['left', 'right'].includes(timedDir.value))
//: 本地实时提示（选横移方向 + 标准系步态）—— 比等服务端返回更早一步
const timedLateralWarn = computed(() => (timedIsLateral.value ? lateralHint(props.basic?.gait) : ''))
//: 后端响应携带的警示（``res.warning``）：本机 basic 数据滞后时的兜底
const timedServerWarn = ref('')
const timedWarn = computed(() => (timedIsLateral.value
  ? (timedLateralWarn.value || timedServerWarn.value)
  : ''))

function clampTimedSpeed () {
  let v = Number(timedSpeed.value)
  if (!isFinite(v) || v <= 0) v = SPEED_DEFAULT
  v = Math.min(SPEED_MAX, Math.max(SPEED_MIN, Math.round(v * 100) / 100))
  timedSpeed.value = v
  return v
}

function clampTimedSeconds () {
  let v = Number(timedSeconds.value)
  if (!isFinite(v) || v <= 0) v = 2
  v = Math.min(TIMED_MAX_S, Math.max(TIMED_MIN_S, Math.round(v * 2) / 2))
  timedSeconds.value = v
  return v
}

// 执行中每 500ms 轮询一次后端状态刷新倒计时（空闲不轮询，避免无谓请求）
let timedPoll = null
function stopTimedPoll () {
  if (timedPoll) { clearInterval(timedPoll); timedPoll = null }
}
function ensureTimedPoll () {
  if (timedPoll || !props.refreshControl) return
  timedPoll = setInterval(() => { props.refreshControl() }, 500)
}
watch(timedActive, (on) => { on ? ensureTimedPoll() : stopTimedPoll() }, { immediate: true })
onUnmounted(stopTimedPoll)

async function startTimed () {
  if (!ctrl.value.enabled) { lastResult.value = '需先开启控制（L1）'; return }
  if (timedActive.value) return
  const dir = TIMED_DIRS[timedDir.value] || TIMED_DIRS.forward
  const s = clampTimedSpeed()
  const secs = clampTimedSeconds()

  // 二次确认：这是会让机器人**真的走起来**的按钮，把方向与时长摆给用户看
  const ok = await askConfirm({
    title: `确认开始定时移动：${dir.label} ${secs}s？`,
    message: `方向：${dir.label}\n速度：${s}（摇杆同刻度）\n时长：${secs} 秒，到点自动零位停止`,
    detail: '移动期间请勿靠近机器人；要提前中止点「中止移动」（零位停止，不触发软急停）。',
    confirmText: '确认开始移动',
    danger: true
  })
  if (!ok) { lastResult.value = '已取消：未开始定时移动'; return }

  const vals = { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 }
  Object.keys(dir.axes).forEach((axis) => {
    vals[axis] = Math.round(dir.axes[axis] * s * 100) / 100
  })
  timedStarting.value = true
  // 先续约：页面刚从后台回来时租约可能已过期，不续约首帧会被租约闸拒发
  if (props.renewLease) { try { await props.renewLease() } catch (e) { /* 忽略 */ } }
  try {
    const res = await props.sendTimedAxis(vals, secs, timedChannel.value)
    timedServerWarn.value = (res && res.warning) || ''
    if (res && res.ok) {
      lastResult.value = `定时移动已开始：${dir.label} ${s} × ${secs}s`
        + `（通道 ${timedChannel.value}，到点自动停止）`
    } else {
      lastResult.value = `被拒：${(res && res.reason) || '未知'} ${(res && res.detail) || ''}`
    }
  } catch (err) {
    timedServerWarn.value = ''
    lastResult.value = '定时移动请求失败：' + (err && err.message ? err.message : err)
  } finally {
    timedStarting.value = false
  }
  if (props.refreshControl) props.refreshControl()
}

async function abortTimed () {
  timedStopping.value = true
  try {
    await props.stopAxis()
    lastResult.value = '已中止定时移动：零位停止（不软急停）'
  } catch (err) {
    lastResult.value = '中止指令下发失败（车侧 150ms 看门狗将自动清零）：'
      + (err && err.message ? err.message : err)
  } finally {
    timedStopping.value = false
  }
  if (props.refreshControl) props.refreshControl()
}

// ---------------------------------------------------------------- 指令
/**
 * 统一下发入口：
 *  · `confirm` 传入则先弹二次确认（危险 / 不可逆动作）；
 *  · 下发期间置 cmdBusy，按钮进加载态并禁用，防止连点重复下发。
 */
async function runCommand (name, params = {}, opts = {}) {
  if (opts.confirm) {
    const ok = await askConfirm(opts.confirm)
    if (!ok) { lastResult.value = `已取消：${CMD_LABEL[name] || name}`; return null }
  }
  if (cmdBusy.value) return null
  cmdBusy.value = name
  try {
    const res = await props.sendCommand(name, params)
    lastResult.value = res.ok
      ? `${CMD_LABEL[name] || name} 已下发`
      : `被拒：${res.reason} ${res.detail || ''}`
    return res
  } catch (err) {
    lastResult.value = `${CMD_LABEL[name] || name} 请求失败：${err && err.message ? err.message : err}`
    return null
  } finally {
    cmdBusy.value = ''
  }
}

/** 切换步态：`want` 是**目标步态**（按钮组传来），不是"当前值取反" */
async function setGait (want) {
  if (want !== undefined && want !== null) gait.value = want
  await runCommand('gait', { param: gait.value })
}

/** 站立：会让机器人**真的动起来**，确认场地与姿态 */
async function onStand () {
  await runCommand('stand_up', {}, {
    confirm: {
      title: '确认让机器人站立？',
      message: '机器人会从当前姿态起立（开机阻尼态下会先完成关节回零再起立）。',
      detail: '请确认机器人周围无人、无障碍物，且地面平整。',
      confirmText: '确认站立',
      danger: true
    }
  })
}

/** 趴下：机身下降，有挤压风险 */
async function onLieDown () {
  await runCommand('lie_down', {}, {
    confirm: {
      title: '确认让机器人趴下？',
      message: '机器人会降低机身趴下。',
      detail: '请确认机身下方与周围没有人员、线缆或其他物品，避免挤压。',
      confirmText: '确认趴下',
      danger: true
    }
  })
}

async function onWake () {
  await runCommand('wake_up')
}

/**
 * 软急停：走**独立端点** props.estop（/api/v1/control/estop），
 * 不能用 sendCommand('estop') 顶替 —— 那是另一条指令通道。
 * 它是会立即改变机器人状态的重要动作，故加二次确认；确认框里也写清"紧急时直接确认"。
 */
async function onEstop () {
  const ok = await askConfirm({
    title: '确认执行软急停？',
    message: '机器人会立即进入阻尼状态并停止运动。',
    detail: '急停后需先「解除急停锁定」才能再次下发运动指令。情况紧急时请直接确认。',
    confirmText: '确认软急停',
    danger: true
  })
  if (!ok) { lastResult.value = '已取消：未执行软急停'; return }
  cmdBusy.value = 'estop'
  try {
    const res = await props.estop()
    lastResult.value = (res && res.ok) ? '软急停已下发' : `被拒：${(res && res.reason) || '未知'}`
  } catch (err) {
    lastResult.value = '软急停请求失败：' + (err && err.message ? err.message : err)
  } finally {
    cmdBusy.value = ''
  }
}

async function onClearEstop () {
  cmdBusy.value = 'clear_estop'
  try {
    const res = await props.clearEstop()
    lastResult.value = (res && res.ok) ? '急停锁定已解除' : `被拒：${(res && res.reason) || '未知'}`
  } catch (err) {
    lastResult.value = '解除急停请求失败：' + (err && err.message ? err.message : err)
  } finally {
    cmdBusy.value = ''
  }
}

/** 开启 / 接管控制权。
 *  force=false：无人占用时的常规申请；
 *  force=true ：接管他人控制权（危险——会把对方踢为只读，且接管前后端会先发
 *               一帧零位把车停下），必须二次确认。 */
async function onEnable (force = false) {
  if (force) {
    const ok = await askConfirm({
      title: `确认从「${ownerText.value}」接管控制权？`,
      message: '接管后对方将转为只读，且接管前会先发一帧零位让机器人停下。',
      detail: '同一时刻只有一个终端能驱动机器人；被接管的终端所有驱动按钮会置灰。',
      confirmText: '确认接管',
      danger: true
    })
    if (!ok) return
  } else {
    const ok = await askConfirm({
      title: '确认开启机器人控制？',
      message: '开启后本终端可以驱动机器人运动（站上全局控制权）。',
      detail: '若控制权已被其他终端占用，开启会失败并提示占用者；此时可改为「接管控制权」。',
      confirmText: '确认开启'
    })
    if (!ok) return
  }
  ctrlBusy.value = 'enable'
  try {
    const res = await props.enableControl(force)
    if (res.ok) {
      lastResult.value = force ? '已接管控制权（对方转为只读）' : '控制已开启（L1）'
      return
    }
    if (res.reason === 'CONTROL_HELD') {
      const who = (res.owner && (res.owner.label || res.owner.session)) || '其他终端'
      lastResult.value = `控制权被「${who}」占用中；如确需操作请点「接管控制权」`
      return
    }
    lastResult.value = `开启失败：${res.reason || ''} ${res.detail || ''}`.trim()
  } catch (err) {
    lastResult.value = '开启控制请求失败：' + (err && err.message ? err.message : err)
  } finally {
    ctrlBusy.value = ''
  }
}

async function onDisable () {
  ctrlBusy.value = 'disable'
  try {
    const res = await props.disableControl()
    lastResult.value = res.ok
      ? '控制已停用（回到 L0 只监）'
      : `释放失败：${res.detail || res.reason || ''}`
  } catch (err) {
    lastResult.value = '释放控制权请求失败：' + (err && err.message ? err.message : err)
  } finally {
    ctrlBusy.value = ''
  }
}
</script>

<style scoped>
/* ---- 分区：把"控制权 / 车侧反馈 / 摇杆 / 定时移动"四块分开 ----
   （.grid 的固定列数规则已收敛到全局 style.css，本面板不再重复定义） */
.msec {
  padding: var(--sp-3);
  margin-bottom: var(--sp-3);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}
.msec:last-of-type { margin-bottom: 0; }

/* ---- 双栏分区 ----
   .mgrid / .mgcol 已收敛为全局工具（style.css）：两个**独立纵向流**，
   避免 grid 按行排布产生的行内大空洞（2026-10-20 实测 302px/335px）。
   分区卡片自身也是 container（.msec），内部 .grid 按卡宽选列数。 */
.msec { container-type: inline-size; }

/* ---- 当前状态一览（2026-10-20）----
   "这台狗现在什么状态"的常驻徽标墙：姿态 / 步态 / 前后补光灯 / 硬急停 / 休眠 /
   充电 / 控制权。四列等宽；断点与 .mgrid 对齐（≤980px 两列、≤560px 单列）——
   分区塌成单列时，状态墙也给足空间，避免"名称 + 徽标"被 ellipsis 截糊。 */
.mstate { margin-bottom: var(--sp-3); }
/* 列数同样按容器宽度（本卡通栏，≈ 内容区宽度）：≥760 四列 / ≥420 两列 / 更窄单列 */
.mstate-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--sp-2) var(--sp-3);
}
@container (min-width: 420px) { .mstate-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@container (min-width: 760px) { .mstate-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }

.mstate-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-width: 0;                 /* 让 pill 里的长文本走 ellipsis，不撑破栅格 */
}
.mstate-k {
  flex: 0 0 auto;
  font-size: var(--fs-12);
  color: var(--muted);
}
.mstate-item .pill { min-width: 0; }
.mstate-v {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.msec-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-2);
  margin-bottom: var(--sp-3);
}

.devbar-label { font-weight: 600; color: var(--text); }
.devbar .hint.err { color: var(--danger); }

.btn-row {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: var(--sp-3);
}

/* 视觉分组：安全类（软急停）与姿态类（站立/趴下）分开 */
.btn-sep {
  width: 1px;
  height: 22px;
  background: var(--line);
  margin: 0 var(--sp-1);
}

/* ---- 虚拟摇杆 ---- */
.joy-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  margin-bottom: var(--sp-3);
}

/* .joy-opts / .joy-radio 已废弃：摇杆模式改用 SegmentedControl（2026-10-20） */

.joy {
  position: relative;
  width: 140px;
  height: 140px;
  margin: 0 auto;
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.45);
  touch-action: none;
  cursor: crosshair;
  user-select: none;
  -webkit-user-select: none;
}

/* 十字参考线 */
.joy::before,
.joy::after {
  content: '';
  position: absolute;
  background: var(--line);
}

.joy::before { left: 50%; top: 12px; bottom: 12px; width: 1px; transform: translateX(-50%); }
.joy::after { top: 50%; left: 12px; right: 12px; height: 1px; transform: translateY(-50%); }

.joy.disabled { opacity: 0.5; filter: grayscale(0.6); }

/* 不可用原因遮罩：pointer-events:none，不挡摇杆自身的 pointer 事件语义 */
.joy-mask {
  position: absolute;
  /* 不越出摇杆盒：此前 inset 左右各 -10px（宽 160 > 盒 140），在窄卡里会
     顶到卡片内边距（2026-10-20 全视口溢出巡检记下的）*/
  inset: auto 0 -34px 0;
  font-size: var(--fs-11);
  line-height: 1.5;
  color: var(--warn);
  text-align: center;
  pointer-events: none;
}

.joy-axis {
  position: absolute;
  font-size: var(--fs-11);
  color: var(--muted);
  pointer-events: none;
}

.joy-axis-top { top: 5px; left: 50%; transform: translateX(-50%); }
.joy-axis-bottom { bottom: 5px; left: 50%; transform: translateX(-50%); }
.joy-axis-left { left: 5px; top: 50%; transform: translateY(-50%); }
.joy-axis-right { right: 5px; top: 50%; transform: translateY(-50%); }

.joy-knob {
  position: absolute;
  z-index: 1;
  width: 44px;
  height: 44px;
  background: var(--accent);
  border: 2px solid rgba(255, 255, 255, 0.85);
  border-radius: 50%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
  transform: translate(-50%, -50%);
  pointer-events: none;
  transition: background var(--t-fast);
}

.joy-knob.active { background: var(--accent-strong); }

.joy-read {
  margin: calc(var(--sp-5) + var(--sp-3)) 0 0;
  font-size: var(--fs-12);
  color: var(--muted);
  text-align: center;
}

.joy-read b { color: var(--text-strong); }

.joy-read .dim { margin-left: 6px; font-size: var(--fs-11); opacity: 0.8; }

.joy-tip {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  text-align: center;
}

.speed-line {
  margin-top: var(--sp-3);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

.speed-line label { font-size: var(--fs-13); }

.speed-line input {
  width: 76px;
  padding: 4px 8px;
  text-align: right;
}

/* ---- 定时移动（2026-10-16 加） ---- */
.timed-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--sp-3);
}

.timed-tip { margin-top: var(--sp-2); }

.last-result {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--muted);
  word-break: break-all;
}

@media (max-width: 560px) {
  .btn-row button { flex: 1 1 auto; }
}
</style>
