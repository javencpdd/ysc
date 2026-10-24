<template>
  <!-- 机器人设置（2026-10-18 加）：补光灯 / 首启回零 / 休眠 / WiFi 热点。
       四项的"能不能验证生效"差别很大，界面上必须分开讲：
         · 补光灯 —— 设备帧 Led.Fill 会自动翻，能闭环验证；
         · 回零开关 —— 车侧对写入**不回帧**，只能再发查询回读；
         · 休眠 —— 写入有应答，但休眠本身不可逆感强，要确认；
         · 热点 —— 走受控 sudo，失败会自动回滚。 -->
  <!-- span-all：本页只有这一个面板，必须占满整行。此前漏了它 —— .pane 的
       列位按"可能存在的下一列"预留，本面板被压成 351px 窄条、1750px 高，
       行内元素还跟着溢出（2026-10-20 实测 317px 容器 / 378px 内容）。
       内部五个分区再分两列独立流（.mgrid/.mgcol），窄屏自动单列。 -->
  <div class="rcfg panel span-all">
    <div class="rcfg-head">
      <span class="rcfg-title">机器人设置</span>
      <span class="pill" :class="control?.enabled ? 'pill-ok' : 'pill-muted'">
        <span class="status-dot" :class="control?.enabled ? 'ok' : 'off'" />
        {{ control?.enabled ? 'L1 可操控' : 'L0 只监' }}
      </span>
      <span v-if="busy !== ''" class="rcfg-busy"><span class="spinner" /> 执行中…</span>
      <span class="spacer" />
      <button
        class="btn-sm btn-ghost"
        type="button"
        :class="{ 'btn-loading': busy === 'refresh' }"
        :disabled="busy !== ''"
        title="重新读取补光灯 / 回零 / 休眠 / 热点的当前值"
        @click="loadAll"
      >{{ busy === 'refresh' ? '读取中…' : '重新读取' }}</button>
    </div>

    <div v-if="!canWrite" class="warn-box">
      当前为<b>只读</b>：需先在「运动控制」页<b>开启控制</b>并取得控制权，才能修改下面的设置。
    </div>

    <div v-if="err" class="danger-box">{{ err }}</div>

    <!-- 五个分区分两列独立流，按实测高度配平（2026-10-20）：
         左列 = 补光灯147 + 雷达默认255 + 回零161 → 587
         右列 = 休眠287 + WiFi热点300            → 599（差 12px）
         用两个纵向流而非 grid 两列，避免行内大空洞（技法同运动控制页）。 -->
    <div class="mgrid">
      <div class="mgcol">

    <!-- ------------------------------------------------ 补光灯 -->
    <section class="rcfg-sec">
      <div class="rcfg-sec-head">补光灯（前后照明）</div>
      <div class="devbar">
        <DeviceToggle
          label="前补光灯"
          :value="fillFront"
          :disabled="!canWrite"
          :busy="busy === 'light'"
          @set="(v) => setFill('front', v)"
        />
        <DeviceToggle
          label="后补光灯"
          :value="fillBack"
          :disabled="!canWrite"
          :busy="busy === 'light'"
          @set="(v) => setFill('back', v)"
        />
        <span v-if="lightPending" class="rcfg-pending">
          <span class="spinner" /> 已下发，等车侧上报（约 1s）
        </span>
      </div>
      <div class="note rcfg-note">
        1101/2 下发，状态在设备帧 <code>Led.Fill</code> 里回读 —— 这一项能闭环验证。
        注意它和设备供电里的「主机电源指示灯 LedHost」不是一回事：那是电源灯，这是照明灯。
      </div>
    </section>

    <!-- ------------------------------------------------ 雷达默认关闭 -->
    <!-- 显式配置开关（2026-10-20 加）：改的是"开机 / 唤醒后的默认行为"，
         不是雷达当前供电。默认关闭 = 不改变既有行为（后端 config 默认 False）。 -->
    <section class="rcfg-sec">
      <div class="rcfg-sec-head">
        雷达默认关闭
        <span class="pill" :class="lidarDefault.enabled ? 'pill-ok' : 'pill-muted'">
          <span class="status-dot" :class="lidarDefault.enabled ? 'ok' : 'off'" />
          {{ lidarDefault.enabled ? '已开启' : '未开启' }}
        </span>
        <span
          v-if="lidarDefault.enabled"
          class="pill pill-muted"
          :title="lidarDefault.source === 'runtime'
            ? '当前值由本页面修改，重启服务后回到部署配置（M20_CONTROL__LIDAR_DEFAULT_OFF）'
            : '当前值来自部署配置（systemd Environment 注入）'"
        >来源：{{ lidarDefault.source === 'runtime' ? '页面设置' : '部署配置' }}</span>
      </div>
      <div class="row rcfg-row">
        <span class="rcfg-kv">开机 / 唤醒后自动关闭</span>
        <span class="rcfg-val">{{ lidarDefault.enabled ? '是' : '否' }}</span>
        <span class="rcfg-kv">雷达当前供电</span>
        <span class="rcfg-val">
          <span class="pill" :class="lidarNowTone.cls">
            <span class="status-dot" :class="lidarNowTone.dot" />
            {{ lidarNowText }}
          </span>
        </span>
        <span class="rcfg-kv">车侧运动状态</span>
        <span class="rcfg-val">{{ lidarDefault.motion_label || '—' }}</span>
        <span class="spacer" />
        <span class="rcfg-kv">最近一次应用</span>
        <span class="rcfg-val" :title="lidarDefault.last_apply?.detail || ''">
          {{ lastApplyText }}
        </span>
      </div>
      <div class="row rcfg-row">
        <button
          class="btn-sm btn-primary"
          type="button"
          :class="{ 'btn-loading': busy === 'lidar_default' }"
          :disabled="busy !== '' || !!lidarDefault.enabled"
          :title="lidarDefault.enabled ? '当前已是「开启」' : '开启后：服务启动、以及任何人点「唤醒整车」之后，都会自动把雷达关掉（需二次确认）'"
          @click="setLidarDefault(true, true)"
        >{{ busy === 'lidar_default' ? '处理中…' : '开启默认关闭' }}</button>
        <button
          class="btn-sm"
          type="button"
          :class="{ 'btn-loading': busy === 'lidar_default' }"
          :disabled="busy !== '' || !lidarDefault.enabled"
          :title="lidarDefault.enabled ? '只关掉这个策略，不会把雷达重新打开（需二次确认）' : '当前已是「关闭」'"
          @click="setLidarDefault(false, false)"
        >{{ busy === 'lidar_default' ? '处理中…' : '关闭策略' }}</button>
        <button
          class="btn-sm"
          type="button"
          :class="{ 'btn-loading': busy === 'lidar_default' }"
          :disabled="busy !== '' || !lidarDefault.enabled"
          :title="lidarDefault.enabled ? '按当前策略立即应用一次（雷达开着且车不在站立/RL 态才会真的下发）' : '策略未开启，无可应用的默认值'"
          @click="applyLidarDefaultNow"
        >{{ busy === 'lidar_default' ? '处理中…' : '立即应用一次' }}</button>
      </div>
      <div class="note rcfg-note">
        <b>这个开关管"以后"，不管"现在"</b>：开启后，服务启动时、以及任何人点「唤醒整车」之后，
        后端会自动下发一次 <code>1101/3 {"Lidar":{"Front":0,"Back":0}}</code>；
        「立即应用一次」就是当次也关掉。关闭策略<b>不会</b>把雷达重新打开 ——
        要开雷达请去「运动控制」页的雷达供电开关。<br />
        <b>影响面（实测）</b>：关雷达后<b>建图 / 定位 / 导航 / 自动回充会失去输入</b>
        （两台主机的 <code>rslidar</code> 会刷超时）；遥测、相机、推流、GPS、网页控制不受影响。
        车在<b>站立 / RL 态时一律不关</b>（与人工操作共用同一道安全闸）。<br />
        运行时修改重启后回到部署配置值（<code>M20_CONTROL__LIDAR_DEFAULT_OFF</code>，默认 false）。
      </div>
    </section>

    <!-- ------------------------------------------------ 首启回零 -->
    <section class="rcfg-sec">
      <div class="rcfg-sec-head">
        首次启动前是否回零
        <span v-if="autoReset.known" class="pill" :class="isStale(autoReset.age_s) ? 'pill-warn' : 'pill-ok'">
          {{ isStale(autoReset.age_s) ? '读数已过期' : '车侧已确认' }}
        </span>
        <span v-else class="pill pill-muted">未知（还没问过车）</span>
      </div>
      <div class="row rcfg-row">
        <span class="rcfg-kv">开机后首次站立前自动回零</span>
        <span class="rcfg-val">{{ autoReset.known ? (autoReset.enable ? '开' : '关') : '—' }}</span>
        <span class="spacer" />
        <button
          class="btn-sm"
          type="button"
          :class="{ 'btn-loading': busy === 'query' }"
          :disabled="busy !== ''"
          title="重新向车侧发一次查询（1101/11）并回读当前值"
          @click="refreshReadback"
        >{{ busy === 'query' ? '读取中…' : '重新读取车侧值' }}</button>
        <button
          class="btn-sm"
          type="button"
          :class="{ 'btn-loading': busy === 'auto_reset' }"
          :disabled="!canWrite || busy !== '' || !autoReset.known || autoReset.enable === true"
          :title="autoReset.enable === true ? '当前已是「开」' : '设为「开」：下次开机首次站立前先标定关节'"
          @click="setAutoReset(true)"
        >{{ busy === 'auto_reset' ? '下发中…' : '开启自动回零' }}</button>
        <button
          class="btn-sm btn-danger"
          type="button"
          :class="{ 'btn-loading': busy === 'auto_reset' }"
          :disabled="!canWrite || busy !== '' || !autoReset.known || autoReset.enable === false"
          :title="autoReset.enable === false ? '当前已是「关」' : '设为「关」：下次开机将不标定直接站立（需二次确认）'"
          @click="setAutoReset(false)"
        >{{ busy === 'auto_reset' ? '下发中…' : '关闭自动回零' }}</button>
      </div>
      <div class="note rcfg-note">
        <b>车侧对「写入」这条指令不回帧</b>（1101/10 实测 3s 无应答，但值确实改了）。
        所以「报文记录」里它会显示 <code>no_response</code> —— 那是"不知道"，不是失败。
        本页点完会自动再发 1101/11 回读，以<b>回读结果</b>为准。
        关掉它，下次开机将不标定直接站立，关节位置未经确认。
      </div>
    </section>

      </div><!-- /.mgcol（左列） -->
      <div class="mgcol">

    <!-- ------------------------------------------------ 休眠 -->
    <section class="rcfg-sec">
      <div class="rcfg-sec-head">
        休眠
        <span v-if="sleep.known" class="pill" :class="isStale(sleep.age_s) ? 'pill-warn' : 'pill-ok'">
          {{ isStale(sleep.age_s) ? '读数已过期' : '车侧已确认' }}
        </span>
        <span v-else class="pill pill-muted">未知（还没问过车）</span>
      </div>
      <div class="row rcfg-row">
        <span class="rcfg-kv">当前状态</span>
        <span class="rcfg-val">
          <span class="pill" :class="sleep.sleeping ? 'pill-warn' : 'pill-ok'">
            {{ sleep.known ? (sleep.sleeping ? '休眠中' : '清醒') : '—' }}
          </span>
        </span>
        <span class="rcfg-kv">自动休眠</span>
        <span class="rcfg-val">{{ sleep.known ? (sleep.auto ? '开' : '关') : '—' }}</span>
        <span class="rcfg-kv">等待时长</span>
        <span class="rcfg-val">{{ sleep.known ? sleep.minutes + ' 分钟' : '—' }}</span>
      </div>
      <div class="row rcfg-row">
        <span class="rcfg-kv">自动休眠</span>
        <button
          class="btn-sm"
          type="button"
          :class="{ 'btn-loading': busy === 'sleep' }"
          :disabled="!canWrite || busy !== '' || sleep.auto === true"
          title="空闲超过设定时长后自动进入休眠"
          @click="setSleepAuto(true)"
        >{{ busy === 'sleep' ? '下发中…' : '开启自动休眠' }}</button>
        <button
          class="btn-sm"
          type="button"
          :class="{ 'btn-loading': busy === 'sleep' }"
          :disabled="!canWrite || busy !== '' || sleep.auto === false"
          title="关闭后机器人不会自动休眠，需手动休眠或断电"
          @click="setSleepAuto(false)"
        >{{ busy === 'sleep' ? '下发中…' : '关闭自动休眠' }}</button>
      </div>
      <div class="row rcfg-row">
        <span class="field">
          <label class="field-label" for="sleep-minutes">空闲等待时长（5~30 分钟）</label>
          <input
            id="sleep-minutes"
            v-model.number="sleepMinutes"
            class="rcfg-num"
            :class="{ 'is-invalid': !!minutesError }"
            type="number"
            min="5"
            max="30"
            step="1"
            :disabled="!canWrite || busy !== ''"
            @input="minutesTouched = true"
          />
        </span>
        <button
          class="btn-sm"
          type="button"
          :class="{ 'btn-loading': busy === 'sleep' }"
          :disabled="!canWrite || busy !== '' || !!minutesError"
          title="把上面的时长写入车侧（自动休眠开关保持当前值不变）"
          @click="setSleepAuto(sleep.auto)"
        >{{ busy === 'sleep' ? '保存中…' : '保存空闲时长' }}</button>
        <span v-if="minutesError" class="field-msg err">{{ minutesError }}</span>
      </div>
      <div class="row rcfg-row">
        <button
          class="btn-sm btn-danger"
          type="button"
          :class="{ 'btn-loading': busy === 'sleep' }"
          :disabled="!canWrite || busy !== ''"
          title="立即进入休眠：会趴下并依次断电（需二次确认）"
          @click="sleepNow"
        >{{ busy === 'sleep' ? '下发中…' : '立即休眠（会趴下）' }}</button>
        <button
          class="btn-sm"
          type="button"
          :class="{ 'btn-loading': busy === 'sleep' }"
          :disabled="!canWrite || busy !== ''"
          title="退出整车休眠（1101/6），会同时恢复相机 / 雷达 / GPS / 关节供电"
          @click="wakeNow"
        >{{ busy === 'sleep' ? '下发中…' : '唤醒整车' }}</button>
      </div>
      <div class="note rcfg-note">
        整车休眠会依次关闭 LED → 风扇 → 视频 → 关节供电并趴下，唤醒后才恢复。
        「自动休眠」只决定空闲多久自动睡，改它<b>不会</b>立刻睡着。
        ⚠️ 时长车侧只接受 5~30 分钟，且<b>超了不报错、直接夹到边界</b>
        （实测填 60 会静默变成 30）。所以这里越界会被后端挡下并提示，不会发给车。
      </div>
    </section>

    <!-- ------------------------------------------------ WiFi 热点 -->
    <section class="rcfg-sec">
      <div class="rcfg-sec-head">
        WiFi 热点
        <span v-if="apReady" class="pill pill-ok">管理入口就绪</span>
        <span v-else class="pill pill-warn">{{ apNote || '不可用' }}</span>
      </div>
      <div class="row rcfg-row">
        <span class="rcfg-kv">热点</span>
        <span class="rcfg-val">
          <span class="pill" :class="pillOf(level(ap.ap))">{{ ap.ap?.summary || '—' }}</span>
        </span>
        <span class="rcfg-kv">上行</span>
        <span class="rcfg-val">
          <span class="pill" :class="pillOf(level(ap.uplink))">{{ ap.uplink?.summary || '—' }}</span>
        </span>
      </div>
      <div v-if="ap.ap && !ap.ap.unknown" class="row rcfg-row">
        <span class="rcfg-kv">SSID</span>
        <span class="rcfg-val mono">{{ ap.ap.ssid || '—' }}</span>
        <span class="rcfg-kv">实际信道</span>
        <span class="rcfg-val num">{{ ap.ap.channel || '—' }}</span>
        <span class="rcfg-kv">网段</span>
        <span class="rcfg-val mono">{{ ap.ap.ip || '—' }}</span>
        <span class="rcfg-kv">已连设备</span>
        <span class="rcfg-val num">{{ ap.ap.clients ?? '—' }}</span>
      </div>
      <!-- 当前密码：默认掩码，点「显示密码」才展开。
           为什么默认掩码：控制台走 HTTP（196 时钟异常，HTTPS 起不来），
           密码是明文过局域网的；且屏幕共享/截图时不会顺手带出去。 -->
      <div v-if="ap.ap && !ap.ap.unknown" class="row rcfg-row">
        <span class="rcfg-kv">当前密码</span>
        <span class="rcfg-val mono" :class="{ 'rcfg-masked': !apPwdShown }">{{ apPasswordText }}</span>
        <button
          v-if="ap.ap.password_set && !ap.ap.password_unreadable"
          class="btn-sm btn-ghost"
          type="button"
          @click="apPwdShown = !apPwdShown"
        >{{ apPwdShown ? '隐藏密码' : '显示密码' }}</button>
      </div>
      <div v-if="ap.sharedRadio" class="warn-box rcfg-note">
        热点与上行<b>共用一块射频</b>，热点的信道由上行决定（配置里写的 2.4G 常被上行拖到 5G）。
        因此<b>只开放 SSID 与密码</b>，频段/信道不给改 —— 改了会与上行走不同信道，
        轻则热点起不来，重则把上行（我们 SSH 的通路）一起带下去。
      </div>
      <div class="row rcfg-row">
        <span class="field">
          <label class="field-label" for="ap-ssid">新 SSID</label>
          <input
            id="ap-ssid"
            v-model.trim="newSsid"
            class="rcfg-text"
            :class="{ 'is-invalid': !!ssidError }"
            placeholder="留空表示不改（1~32 个字符）"
          />
        </span>
        <span class="field">
          <label class="field-label" for="ap-pwd">新密码</label>
          <input
            id="ap-pwd"
            v-model="newPassword"
            class="rcfg-text"
            :class="{ 'is-invalid': !!pwdError }"
            type="password"
            placeholder="留空表示不改（8~63 位）"
            autocomplete="new-password"
          />
        </span>
        <button
          class="btn-sm"
          type="button"
          :class="{ 'btn-primary': canSetAp, 'btn-loading': busy === 'ap' }"
          :disabled="busy !== '' || !canSetAp"
          :title="setApTitle"
          @click="setAp"
        >{{ busy === 'ap' ? '写入中…' : '保存热点设置' }}</button>
      </div>
      <div v-if="ssidError || pwdError" class="rcfg-row">
        <span v-if="ssidError" class="field-msg err">SSID：{{ ssidError }}</span>
        <span v-if="pwdError" class="field-msg err">密码：{{ pwdError }}</span>
      </div>
      <div class="note rcfg-note">
        改热点会让<b>已连设备全部掉线</b>并重连。两个输入框<b>留空即表示该项不改</b> ——
        实测只改 SSID 时密码文件校验和不变，所以不必为了改个名字而去打听旧密码。
        写入失败会自动回滚到原值；若上行也因此中断，脚本会优先抢救上行。
        <br />
        控制台走 HTTP（196 时钟异常，HTTPS 起不来），当前密码是明文过局域网的，
        因此默认打掩码 —— 需要念给别人听或截图时再点「显示密码」。
      </div>
    </section>

      </div><!-- /.mgcol（右列） -->
    </div><!-- /.mgrid -->
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import DeviceToggle from './DeviceToggle.vue'
import { getJson, postJson } from '../api/index.js'
import { askConfirm } from '../composables/useConfirm.js'

const props = defineProps({
  /** 控制通道状态（L0/L1）。写方向操作一律看它。 */
  control: { type: Object, default: () => ({}) },
  /** 设备帧（1002/5），补光灯状态来源于它的 fill_front / fill_back */
  device: { type: Object, default: () => ({}) },
  /** 本终端是否持有控制权（多操作员互斥）：非 owner 时写按钮置灰，
   *  否则点了必被后端拒（NOT_OWNER），用户只会以为面板坏了。 */
  isControlOwner: { type: Boolean, default: true }
})

// ⚠️ ref 一律在 setup 顶层声明并在模板里直接用顶层名。
//    composable 返回普通对象时，模板拿 dev.busy 会拿到 Ref 本身（恒真）
//    → 所有按钮被永久禁用（2026-10-17 真踩，ADR-020）。
const cfg = ref({ fill_light: {}, auto_reset: {}, sleep: {}, lidar_default: {} })
const ap = ref({})
const busy = ref('')
const err = ref('')
const lightPending = ref(false)
const sleepMinutes = ref(10)
const minutesTouched = ref(false)
const newSsid = ref('')
const newPassword = ref('')
const apReady = ref(true)
const apNote = ref('')
const apPwdShown = ref(false)
let timer = null
let lightTimer = null

// 写方向 = 开启控制（L1）**且**本终端持有控制权（多操作员互斥）。
const canWrite = computed(() => !!(props.control?.enabled && props.isControlOwner))
const fillFront = computed(() => nullOr(props.device?.fill_front))
const fillBack = computed(() => nullOr(props.device?.fill_back))
const autoReset = computed(() => cfg.value.auto_reset || {})
const sleep = computed(() => cfg.value.sleep || {})
// 雷达默认关闭策略状态（随 /robot/config 一起返回，见后端 MonitorService.robot_config）
const lidarDefault = computed(() => cfg.value.lidar_default || {})
const lidarNow = computed(() => lidarDefault.value.lidar_now || null)

// 雷达当前供电的展示：上报值不是布尔（0=关 / 1=启动中 / 2=运行中），
// 一律按"非 0 即开"显示 —— 与后端 device_switch_is_off 同一口径。
const lidarNowText = computed(() => {
  const l = lidarNow.value
  if (!l) return '未知'
  const on = (v) => (Number(v) ? '开' : '关')
  return `前 ${on(l.Front)} / 后 ${on(l.Back)}`
})
const lidarNowTone = computed(() => {
  const l = lidarNow.value
  if (!l) return { cls: 'pill-muted', dot: 'off' }
  const anyOn = Object.values(l).some((v) => Number(v))
  return anyOn ? { cls: 'pill-ok', dot: 'ok' } : { cls: 'pill-muted', dot: 'off' }
})

// 最近一次应用结果：把后端的 outcome/reason 翻译成"人话"，
// 悬停标题里保留后端原始 detail（排查时要能看到真实原因）。
const APPLY_TEXT = {
  never: '从未应用',
  applied: '已下发关闭雷达',
  already_off: '雷达已是关闭状态，未下发',
  motion_locked: '站立 / RL 态，按安全闸跳过',
  too_soon: '距上次不足 10s，已跳过',
  no_device_data: '未收到设备帧，无法判断',
  disabled: '策略未开启'
}
const lastApplyText = computed(() => {
  const la = lidarDefault.value.last_apply || {}
  if (!la.outcome) return '—'
  if (la.outcome === 'failed') return `下发失败：${la.reason || '未知'}`
  const base = APPLY_TEXT[la.reason] || (la.outcome === 'applied' ? '已应用' : '已跳过')
  return la.trigger ? `${base}（${la.trigger}）` : base
})

// ---- 表单即时校验（只做前端提示，判定仍以后端为准）----
// 阈值与后端 ap_ctl.py 一致：SSID 1~32 可打印字符 / WPA 密码 8~63 位。
const SSID_MIN = 1, SSID_MAX = 32, PWD_MIN = 8, PWD_MAX = 63

const ssidError = computed(() => {
  const s = newSsid.value
  if (!s) return ''
  if (s.length < SSID_MIN || s.length > SSID_MAX) {
    return `需 ${SSID_MIN}~${SSID_MAX} 个字符，当前 ${s.length} 个`
  }
  // 后端只挡"不可打印字符"，中文/全角会占多个字节且不一定可打印，一并提示
  if (/[^\x20-\x7E]/.test(s)) return '含中文或不可打印字符，热点可能起不来'
  return ''
})

const pwdError = computed(() => {
  const p = newPassword.value
  if (!p) return ''
  if (p.length < PWD_MIN || p.length > PWD_MAX) {
    return `WPA 密码需 ${PWD_MIN}~${PWD_MAX} 位，当前 ${p.length} 位`
  }
  return ''
})

const minutesError = computed(() => {
  const v = Number(sleepMinutes.value)
  if (!Number.isFinite(v)) return '请填写数字'
  if (v < 5 || v > 30) return '车侧只接受 5~30 分钟，超范围会被夹到边界'
  return ''
})

const canSetAp = computed(() => !!(newSsid.value || newPassword.value)
  && apReady.value && !ssidError.value && !pwdError.value)

/** 保存按钮的禁用原因要讲清楚，而不是让人猜为什么点不动 */
const setApTitle = computed(() => {
  if (!apReady.value) return `热点入口不可用：${apNote.value || '未知原因'}`
  if (ssidError.value) return `SSID 不合法：${ssidError.value}`
  if (pwdError.value) return `密码不合法：${pwdError.value}`
  if (!(newSsid.value || newPassword.value)) return '请至少填写新 SSID 或新密码（留空表示不改）'
  return '写入后已连设备会全部掉线（需二次确认）'
})

/**
 * 当前密码的展示文本。
 *
 * 四种状态必须分开说，不能一概显示成八个点：
 *  · 没设密码     → 开放网络（此时谁都能连，反而是该提醒的）
 *  · 有但读不出原文 → 含控制字符/首尾空白，显示一个连不上的密码比不显示更糟
 *  · 已掩码       → 默认态，避免截图/屏幕共享顺手带出去
 *  · 已展开       → 用户主动点了「显示密码」
 */
const apPasswordText = computed(() => {
  const a = ap.value?.ap
  if (!a || a.unknown) return '—'
  if (!a.password_set) return '未设置密码（开放网络，谁都能连）'
  if (a.password_unreadable) return '有密码，但含特殊字符，读不出原文'
  return apPwdShown.value ? String(a.password) : '••••••••'
})

function nullOr (v) {
  return (v === null || v === undefined) ? null : Number(v)
}

function isStale (age) {
  return typeof age === 'number' && age > 30
}

function level (g) {
  return g?.level || 'off'
}

/** 后端 level → 全站统一的 pill 语义色 */
function pillOf (lv) {
  return ({ ok: 'pill-ok', warn: 'pill-warn', off: 'pill-muted' })[lv] || 'pill-muted'
}

// ---------------------------------------------------------------- 读取
async function loadAll () {
  const prev = busy.value
  busy.value = 'refresh'
  try {
    cfg.value = await getJson('/api/v1/robot/config')
  } catch (e) {
    cfg.value = { fill_light: {}, auto_reset: {}, sleep: {}, lidar_default: {} }
  } finally {
    busy.value = prev
  }
  // 把车侧读回的分钟数同步到输入框：车上是 25 而框里还是默认 10 的话，
  // 点「唤醒整车」会把车侧的 25 覆盖成 10。用户手改过就不再自动覆盖。
  const m = cfg.value?.sleep?.minutes
  if (typeof m === 'number' && m > 0 && !minutesTouched.value) {
    sleepMinutes.value = m
  }
  await loadAp()
}

async function loadAp () {
  try {
    const res = await getJson('/api/v1/net/ap')
    ap.value = res || {}
    apReady.value = res?.ok !== false
    apNote.value = res?.ok === false ? (res.reason || '不可用') : ''
  } catch (e) {
    ap.value = {}
    apReady.value = false
    apNote.value = '读取失败'
  }
}

/**
 * 主动问车（1101/11 + 1101/7）。
 * 读值是**异步**的：这里只负责发问，应答落到后端查询缓存后由下一次 loadAll 读到。
 * 所以固定「先问 → 等 1.2s → 再读」，省掉让用户干等。
 */
async function refreshReadback () {
  busy.value = 'query'
  err.value = ''
  try {
    await postJson('/api/v1/robot/config/refresh', {})
  } catch (e) {
    err.value = '查询发送失败：' + (e?.message || e)
    busy.value = ''
    return
  }
  busy.value = ''
  await sleepMs(1200)
  await loadAll()
}

// ---------------------------------------------------------------- 补光灯
async function setFill (side, wantOn) {
  // 1101/2 是整键下发：开前灯也要把后灯当前值一起带上，缺一路等于把另一路关掉
  const front = side === 'front' ? wantOn : (fillFront.value ?? 0)
  const back = side === 'back' ? wantOn : (fillBack.value ?? 0)
  busy.value = 'light'
  err.value = ''
  lightPending.value = true
  try {
    const res = await postJson('/api/v1/robot/light', {
      front: !!front, back: !!back
    })
    if (!res?.ok) {
      err.value = `补光灯下发被拒：${res?.reason || '未知'} ${res?.detail || ''}`
    }
  } catch (e) {
    err.value = '补光灯请求失败：' + (e?.message || e)
  } finally {
    busy.value = ''
    if (lightTimer) clearTimeout(lightTimer)
    // 车侧上报有约 1s 滞后，等一会儿再撤提示
    lightTimer = setTimeout(() => { lightPending.value = false }, 2500)
  }
}

// ---------------------------------------------------------------- 雷达默认关闭
// 与别的设置项的区别：它**不改车侧当前值**，改的是"开机 / 唤醒后的默认行为"。
// 开启时默认立即应用一次（apply_now），所以确认弹窗要把"当次就会关雷达"讲清楚。
async function setLidarDefault (enabled, applyNow) {
  const what = enabled ? '开启「雷达默认关闭」' : '关闭「雷达默认关闭」策略'
  const ok = await askConfirm({
    title: `确认${what}？`,
    message: enabled
      ? '开启后：服务启动时、以及任何人点「唤醒整车」之后，后端都会自动关闭雷达供电；'
        + '并会立即应用一次（雷达开着且车不在站立 / RL 态时）。'
      : '关闭后：不再自动关闭雷达。注意这不会把雷达重新打开，需要时请到「运动控制」页手动开。',
    detail: '关雷达后建图 / 定位 / 导航 / 自动回充会失去输入（两台主机的 rslidar 会刷超时）；'
      + '遥测、相机、推流、GPS 不受影响。站立 / RL 态下按安全闸跳过，不会真的关。'
      + '运行时修改在服务重启后回到部署配置值。',
    confirmText: enabled ? '确认开启' : '确认关闭策略',
    danger: !!enabled
  })
  if (!ok) return
  busy.value = 'lidar_default'
  err.value = ''
  try {
    const res = await postJson('/api/v1/robot/lidar-default', {
      enabled: !!enabled, confirmed: true, apply_now: !!applyNow
    })
    if (!res?.ok) {
      err.value = `雷达默认策略下发被拒：${res?.reason || '未知'} ${res?.detail || ''}`
    } else if (res.applied && res.applied.outcome === 'failed') {
      err.value = `策略已保存，但本次应用失败：${res.applied.detail || res.applied.reason}`
    }
  } catch (e) {
    err.value = '雷达默认策略请求失败：' + (e?.message || e)
  } finally {
    busy.value = ''
    await loadAll()
  }
}

/** 立即应用一次：策略已开启时，按当前条件（雷达开着 + 非站立/RL）真下发一次 */
async function applyLidarDefaultNow () {
  const ok = await askConfirm({
    title: '确认立即应用「雷达默认关闭」？',
    message: '会按当前策略立即下发一次关闭雷达（仅当雷达当前开着、且车不在站立 / RL 态）。',
    detail: '与人工关闭雷达走同一道安全闸；站立 / RL 态会被拒绝并提示。',
    confirmText: '确认应用',
    danger: true
  })
  if (!ok) return
  await setLidarDefault(true, true)
}

// ---------------------------------------------------------------- 首启回零
async function setAutoReset (enable) {
  if (!enable) {
    const ok = await askConfirm({
      title: '确认关闭「首次启动前自动回零」？',
      message: '关掉后，下次开机首次站立将不再先回零，关节位置未经标定。',
      detail: '车侧对这条写入不回帧，「报文记录」里会显示「无响应」——那是"不知道"，不是失败。'
        + '本页会在写入后自动重新读取车侧值以确认结果。',
      confirmText: '确认关闭回零',
      danger: true
    })
    if (!ok) return
  }
  busy.value = 'auto_reset'
  err.value = ''
  try {
    const res = await postJson('/api/v1/robot/auto_reset', {
      enable: !!enable, confirmed: true
    })
    if (!res?.ok) {
      err.value = `回零开关下发被拒：${res?.reason || '未知'} ${res?.detail || ''}`
      busy.value = ''
      return
    }
  } catch (e) {
    err.value = '回零开关请求失败：' + (e?.message || e)
    busy.value = ''
    return
  }
  busy.value = ''
  // ★车侧对写入不回帧，必须回读才知道成没成
  await sleepMs(600)
  await refreshReadback()
}

// ---------------------------------------------------------------- 休眠
async function setSleepAuto (auto) {
  await sendSleep({ sleep: false, auto: !!auto, minutes: sleepMinutes.value })
}

async function sleepNow () {
  const ok = await askConfirm({
    title: '确认让整车进入休眠？',
    message: '机器人会趴下，并依次关闭 LED / 风扇 / 视频 / 关节供电。',
    detail: '唤醒后才恢复。休眠期间相机画面与大部分遥测都会中断。',
    confirmText: '确认立即休眠',
    danger: true
  })
  if (!ok) return
  await sendSleep({
    sleep: true, auto: !!sleep.value.auto, minutes: sleepMinutes.value,
    confirmed: true
  })
}

async function wakeNow () {
  await sendSleep({
    sleep: false, auto: !!sleep.value.auto, minutes: sleepMinutes.value
  })
}

async function sendSleep (body) {
  busy.value = 'sleep'
  err.value = ''
  try {
    const res = await postJson('/api/v1/robot/sleep', body)
    if (!res?.ok) {
      err.value = `休眠操作被拒：${res?.reason || '未知'} ${res?.detail || ''}`
      busy.value = ''
      return
    }
  } catch (e) {
    err.value = '休眠请求失败：' + (e?.message || e)
    busy.value = ''
    return
  }
  busy.value = ''
  await sleepMs(1200)
  await refreshReadback()
}

// ---------------------------------------------------------------- 热点
async function setAp () {
  const parts = []
  if (newSsid.value) parts.push(`SSID → ${newSsid.value}`)
  if (newPassword.value) parts.push('密码 → 已设置（不回显）')
  const ok = await askConfirm({
    title: '确认写入热点配置？',
    message: parts.join('\n'),
    detail: '已连设备会全部掉线并需重新连接。写入失败会自动回滚；若上行中断，脚本会优先抢救上行。',
    confirmText: '确认写入',
    danger: true
  })
  if (!ok) return
  busy.value = 'ap'
  err.value = ''
  try {
    const res = await postJson('/api/v1/net/ap', {
      ssid: newSsid.value || null,
      password: newPassword.value || null,
      confirmed: true
    })
    if (res?.ok) {
      newSsid.value = ''
      newPassword.value = ''
      apPwdShown.value = false   // 密码可能变了，重新掩上
    } else {
      err.value = `热点写入被拒：${res?.reason || '未知'} ${res?.detail || ''}`
    }
    // applied / rolled_back 都要把新状态展示出来（回滚了更要让人看见）
    if (res && (res.ap || res.uplink)) ap.value = res
  } catch (e) {
    err.value = '热点请求失败：' + (e?.message || e)
  } finally {
    busy.value = ''
  }
  await loadAp()
}

function sleepMs (ms) {
  return new Promise((r) => setTimeout(r, ms))
}

onMounted(() => {
  loadAll()
  refreshReadback()
  timer = setInterval(loadAll, 6000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (lightTimer) clearTimeout(lightTimer)
})
</script>

<style scoped>
/* 分区卡片：与运动控制页的 .msec 同一套外观令牌（panel-2 底 / r-md 圆角 /
   1px 线 / sp-3 内边距），全站卡片语言统一；两列之间用 gap 分隔，
   不再用 border-bottom 横贯整行（分列后横线会断在列中间，很难看）。 */
.rcfg { font-size: var(--fs-12); }
.rcfg { container-type: inline-size; }

.rcfg-sec {
  padding: var(--sp-3);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--panel-2);
}

.rcfg-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
  padding-bottom: var(--sp-2);
  border-bottom: 1px solid var(--line);
}

.rcfg-title { font-weight: 600; font-size: var(--fs-15); color: var(--text); }

.rcfg-busy {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-11);
  color: var(--accent);
}


.rcfg-sec-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
  font-weight: 600;
  font-size: var(--fs-13);
  color: var(--text);
}

/* 行：窄屏（单列 404px）下两个 190px 输入框 + 按钮会溢出 404-378=26px，
   故允许换行 + 输入框可收缩（max-width:100% 防止 fixed width 撑破）。 */
.rcfg-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-1) 0;
}

.rcfg-kv { color: var(--muted); }
.rcfg-val { font-variant-numeric: tabular-nums; color: var(--text); min-width: 0; }
/* 值可能是长 SSID / 长摘要（如 "CA9B_NO.1273_24G"），.pill 默认 nowrap 会顶破
   窄屏单列（实测 420px 下溢出 13px）—— 设置页内的 pill 允许换行 */
.rcfg-val .pill { white-space: normal; }
.rcfg-val.mono { font-family: var(--ff-mono); }
/* 掩码态：压低对比度，让"展开"成为有意的动作而非默认可见 */
.rcfg-val.rcfg-masked { color: var(--muted); letter-spacing: 1px; user-select: none; }

.rcfg-note { margin-top: var(--sp-2); }
.rcfg-note code {
  padding: 0 4px;
  font-family: var(--ff-mono);
  font-size: var(--fs-11);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-xs);
}

.rcfg-pending {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-11);
  color: var(--accent);
}

.rcfg-num { width: 76px; max-width: 100%; text-align: right; }
.rcfg-text { flex: 1 1 190px; width: 190px; max-width: 100%; min-width: 0; }

@media (max-width: 560px) {
  .rcfg-text { width: 100%; }
}
</style>
