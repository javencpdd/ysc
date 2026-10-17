<template>
  <!-- 机器人设置（2026-10-18 加）：补光灯 / 首启回零 / 休眠 / WiFi 热点。
       四项的"能不能验证生效"差别很大，界面上必须分开讲：
         · 补光灯 —— 设备帧 Led.Fill 会自动翻，能闭环验证；
         · 回零开关 —— 车侧对写入**不回帧**，只能再发查询回读；
         · 休眠 —— 写入有应答，但休眠本身不可逆感强，要确认；
         · 热点 —— 走受控 sudo，失败会自动回滚。 -->
  <div class="rcfg">
    <div class="rcfg-head">
      <span class="rcfg-title">机器人设置</span>
      <span class="rcfg-spacer" />
      <span class="rcfg-l1" :class="{ on: control?.enabled }">
        {{ control?.enabled ? 'L1 可写' : 'L0 只监' }}
      </span>
      <button class="mini" type="button" :disabled="busy !== ''" @click="loadAll">刷新</button>
    </div>

    <div v-if="err" class="rcfg-err">{{ err }}</div>

    <!-- ------------------------------------------------ 补光灯 -->
    <section class="rcfg-sec">
      <div class="rcfg-sec-head">补光灯（前后照明）</div>
      <div class="rcfg-row">
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
        <span v-if="lightPending" class="rcfg-pending">已下发，等车侧上报（约 1s）</span>
      </div>
      <div class="rcfg-note">
        1101/2 下发，状态在设备帧 <code>Led.Fill</code> 里回读 —— 这一项能闭环验证。
        注意它和设备供电里的「主机电源指示灯 LedHost」不是一回事：那是电源灯，这是照明灯。
      </div>
    </section>

    <!-- ------------------------------------------------ 首启回零 -->
    <section class="rcfg-sec">
      <div class="rcfg-sec-head">
        首次启动前是否回零
        <span v-if="autoReset.known" class="rcfg-verified" :class="{ stale: isStale(autoReset.age_s) }">
          {{ isStale(autoReset.age_s) ? '读数已过期' : '车侧已确认' }}
        </span>
        <span v-else class="rcfg-unknown">未知（还没问过车）</span>
      </div>
      <div class="rcfg-row">
        <span class="rcfg-kv">开机后首次站立前自动回零</span>
        <span class="rcfg-val">{{ autoReset.known ? (autoReset.enable ? '开' : '关') : '—' }}</span>
        <button class="mini" type="button" :disabled="busy !== ''" @click="refreshReadback">
          重新回读
        </button>
        <button
          class="mini"
          type="button"
          :disabled="!canWrite || busy !== '' || !autoReset.known"
          @click="setAutoReset(true)"
        >设为开</button>
        <button
          class="mini"
          type="button"
          :disabled="!canWrite || busy !== '' || !autoReset.known"
          @click="setAutoReset(false)"
        >设为关</button>
      </div>
      <div class="rcfg-note">
        <b>车侧对「写入」这条指令不回帧</b>（1101/10 实测 3s 无应答，但值确实改了）。
        所以「报文记录」里它会显示 <code>no_response</code> —— 那是"不知道"，不是失败。
        本页点完会自动再发 1101/11 回读，以<b>回读结果</b>为准。
        关掉它，下次开机将不标定直接站立，关节位置未经确认。
      </div>
    </section>

    <!-- ------------------------------------------------ 休眠 -->
    <section class="rcfg-sec">
      <div class="rcfg-sec-head">
        休眠
        <span v-if="sleep.known" class="rcfg-verified" :class="{ stale: isStale(sleep.age_s) }">
          {{ isStale(sleep.age_s) ? '读数已过期' : '车侧已确认' }}
        </span>
        <span v-else class="rcfg-unknown">未知（还没问过车）</span>
      </div>
      <div class="rcfg-row">
        <span class="rcfg-kv">当前状态</span>
        <span class="rcfg-val" :class="{ danger: sleep.sleeping }">
          {{ sleep.known ? (sleep.sleeping ? '休眠中' : '清醒') : '—' }}
        </span>
        <span class="rcfg-kv">自动休眠</span>
        <span class="rcfg-val">{{ sleep.known ? (sleep.auto ? '开' : '关') : '—' }}</span>
        <span class="rcfg-kv">等待时长</span>
        <span class="rcfg-val">{{ sleep.known ? sleep.minutes + ' 分钟' : '—' }}</span>
      </div>
      <div class="rcfg-row">
        <span class="rcfg-kv">自动休眠</span>
        <button
          class="mini"
          type="button"
          :disabled="!canWrite || busy !== ''"
          @click="setSleepAuto(true)"
        >开</button>
        <button
          class="mini"
          type="button"
          :disabled="!canWrite || busy !== ''"
          @click="setSleepAuto(false)"
        >关</button>
        <span class="rcfg-kv">时长（5~30 分钟）</span>
        <input
          v-model.number="sleepMinutes"
          class="rcfg-num"
          type="number"
          min="5"
          max="30"
          step="1"
          @input="minutesTouched = true"
        />
        <button
          class="mini"
          type="button"
          :disabled="!canWrite || busy !== ''"
          @click="setSleepAuto(sleep.auto)"
        >应用时长</button>
      </div>
      <div class="rcfg-row">
        <button
          class="mini danger"
          type="button"
          :disabled="!canWrite || busy !== ''"
          @click="sleepNow"
        >立即休眠（会趴下）</button>
        <button
          class="mini"
          type="button"
          :disabled="!canWrite || busy !== ''"
          @click="wakeNow"
        >唤醒整车</button>
      </div>
      <div class="rcfg-note">
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
        <span v-if="apReady" class="rcfg-verified">受控入口已就绪</span>
        <span v-else class="rcfg-unknown">{{ apNote }}</span>
      </div>
      <div class="rcfg-row">
        <span class="rcfg-kv">热点</span>
        <span class="rcfg-val" :class="level(ap.ap)">{{ ap.ap?.summary || '—' }}</span>
        <span class="rcfg-kv">上行</span>
        <span class="rcfg-val" :class="level(ap.uplink)">{{ ap.uplink?.summary || '—' }}</span>
      </div>
      <div v-if="ap.ap && !ap.ap.unknown" class="rcfg-row">
        <span class="rcfg-kv">SSID</span>
        <span class="rcfg-val mono">{{ ap.ap.ssid || '—' }}</span>
        <span class="rcfg-kv">实际信道</span>
        <span class="rcfg-val mono">{{ ap.ap.channel || '—' }}</span>
        <span class="rcfg-kv">网段</span>
        <span class="rcfg-val mono">{{ ap.ap.ip || '—' }}</span>
        <span class="rcfg-kv">已连设备</span>
        <span class="rcfg-val mono">{{ ap.ap.clients ?? '—' }}</span>
      </div>
      <div v-if="ap.sharedRadio" class="rcfg-warn">
        热点与上行<b>共用一块射频</b>，热点的信道由上行决定（配置里写的 2.4G 常被上行拖到 5G）。
        因此<b>只开放 SSID 与密码</b>，频段/信道不给改 —— 改了会与上行走不同信道，
        轻则热点起不来，重则把上行（我们 SSH 的通路）一起带下去。
      </div>
      <div class="rcfg-row">
        <span class="rcfg-kv">新 SSID</span>
        <input v-model.trim="newSsid" class="rcfg-text" placeholder="字母/数字/_-，1~32 位" />
        <span class="rcfg-kv">新密码</span>
        <input
          v-model="newPassword"
          class="rcfg-text"
          type="password"
          placeholder="留空表示不改（8~63 位）"
          autocomplete="new-password"
        />
        <button class="mini" type="button" :disabled="busy !== '' || !canSetAp" @click="setAp">
          写入热点
        </button>
      </div>
      <div class="rcfg-note">
        改热点会让<b>已连设备全部掉线</b>并重连。密码<b>不会被读出来</b>，只会显示是否已设置。
        写入失败会自动回滚到原值；若上行也因此中断，脚本会优先抢救上行。
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import DeviceToggle from './DeviceToggle.vue'
import { getJson, postJson } from '../api/index.js'

const props = defineProps({
  /** 控制通道状态（L0/L1）。写方向操作一律看它。 */
  control: { type: Object, default: () => ({}) },
  /** 设备帧（1002/5），补光灯状态来源于它的 fill_front / fill_back */
  device: { type: Object, default: () => ({}) }
})

// ⚠️ ref 一律在 setup 顶层声明并在模板里直接用顶层名。
//    composable 返回普通对象时，模板拿 dev.busy 会拿到 Ref 本身（恒真）
//    → 所有按钮被永久禁用（2026-10-17 真踩，ADR-020）。
const cfg = ref({ fill_light: {}, auto_reset: {}, sleep: {} })
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
let timer = null
let lightTimer = null

const canWrite = computed(() => !!props.control?.enabled)
const fillFront = computed(() => nullOr(props.device?.fill_front))
const fillBack = computed(() => nullOr(props.device?.fill_back))
const autoReset = computed(() => cfg.value.auto_reset || {})
const sleep = computed(() => cfg.value.sleep || {})
const canSetAp = computed(
  () => !!(newSsid.value || newPassword.value) && apReady.value)

function nullOr (v) {
  return (v === null || v === undefined) ? null : Number(v)
}

function isStale (age) {
  return typeof age === 'number' && age > 30
}

function level (g) {
  return g?.level || 'off'
}

// ---------------------------------------------------------------- 读取
async function loadAll () {
  try {
    cfg.value = await getJson('/api/v1/robot/config')
  } catch (e) {
    cfg.value = { fill_light: {}, auto_reset: {}, sleep: {} }
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
    return
  } finally {
    busy.value = ''
  }
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

// ---------------------------------------------------------------- 首启回零
async function setAutoReset (enable) {
  if (!enable) {
    const ok = window.confirm(
      '确认关闭「首次启动前自动回零」？\n\n' +
      '关掉后，下次开机首次站立将不再先回零，关节位置未经标定。'
    )
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
      return
    }
  } catch (e) {
    err.value = '回零开关请求失败：' + (e?.message || e)
    return
  } finally {
    busy.value = ''
  }
  // ★车侧对写入不回帧，必须回读才知道成没成
  await sleepMs(600)
  await refreshReadback()
}

// ---------------------------------------------------------------- 休眠
async function setSleepAuto (auto) {
  await sendSleep({ sleep: false, auto: !!auto, minutes: sleepMinutes.value })
}

async function sleepNow () {
  const ok = window.confirm(
    '确认让整车进入休眠？\n\n' +
    '会依次关闭 LED / 风扇 / 视频 / 关节供电并趴下，唤醒后才恢复。'
  )
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
      return
    }
  } catch (e) {
    err.value = '休眠请求失败：' + (e?.message || e)
    return
  } finally {
    busy.value = ''
  }
  await sleepMs(1200)
  await refreshReadback()
}

// ---------------------------------------------------------------- 热点
async function setAp () {
  const parts = []
  if (newSsid.value) parts.push(`SSID → ${newSsid.value}`)
  if (newPassword.value) parts.push('密码 → 已设置（不回显）')
  const ok = window.confirm(
    `确认写入热点配置？\n\n${parts.join('\n')}\n\n` +
    '已连设备会全部掉线并需重新连接。'
  )
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
.rcfg {
  margin-bottom: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: var(--panel-2, #f7f8fa);
  border: 1px solid var(--border, #d8dce3);
  border-radius: 6px;
}
.rcfg-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.rcfg-title { font-weight: 600; }
.rcfg-spacer { flex: 1 1 auto; }
.rcfg-l1 { color: var(--muted, #888); }
.rcfg-l1.on { color: var(--ok, #2e9e5b); }
.rcfg-sec {
  padding: 6px 0 8px;
  border-top: 1px solid var(--line, #e3e6eb);
}
.rcfg-sec-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-weight: 600;
}
.rcfg-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
}
.rcfg-kv { color: var(--muted, #888); }
.rcfg-val { font-variant-numeric: tabular-nums; }
.rcfg-val.mono { font-family: var(--mono, ui-monospace, monospace); }
.rcfg-val.ok { color: var(--ok, #2e9e5b); }
.rcfg-val.warn { color: var(--warn, #c47f17); }
.rcfg-val.off, .rcfg-kv { }
.rcfg-val.danger { color: var(--danger, #d0453b); }
.rcfg-verified { color: var(--ok, #2e9e5b); font-weight: 400; font-size: 11px; }
.rcfg-verified.stale { color: var(--warn, #c47f17); }
.rcfg-unknown, .rcfg-pending { color: var(--muted, #888); font-weight: 400; font-size: 11px; }
.rcfg-note {
  margin-top: 4px;
  line-height: 1.65;
  color: var(--muted, #777);
}
.rcfg-warn {
  margin: 4px 0;
  padding: 4px 6px;
  line-height: 1.6;
  color: var(--warn, #a4630c);
  background: var(--warn-bg, #fdf6e7);
  border: 1px solid var(--warn-line, #f0d9a8);
  border-radius: 4px;
}
.rcfg-err { color: var(--danger, #d0453b); }
.rcfg-num { width: 64px; padding: 1px 4px; font-family: inherit; font-size: 12px; }
.rcfg-text { width: 150px; padding: 1px 5px; font-family: inherit; font-size: 12px; }
.mini {
  padding: 1px 8px;
  font-size: 11px;
  font-family: inherit;
  color: var(--muted, #888);
  background: transparent;
  border: 1px solid var(--line, #d8dce3);
  border-radius: 4px;
}
.mini:hover:not(:disabled) { color: var(--text, #222); border-color: var(--accent, #2f6fed); }
.mini:disabled { opacity: 0.5; }
.mini.danger { color: var(--danger, #d0453b); }
.mini.danger:hover:not(:disabled) { border-color: var(--danger, #d0453b); }
</style>
