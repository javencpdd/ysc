<template>
  <div class="panel" :class="{ stale: isStale('basic') }">
    <h3>
      基础状态
      <small>（1002/6 · 2Hz）</small>
    </h3>
    <div class="grid">
      <div class="kv">
        <span>运动状态</span>
        <span><span class="pill" :class="motionPill">{{ b.motion_state_label || '—' }}</span></span>
      </div>
      <div class="kv"><span>步态</span><span>{{ b.gait_label || '—' }}</span></div>
      <div class="kv"><span>使用模式</span><span>{{ b.control_usage_mode_label || '—' }}</span></div>
      <div class="kv"><span>充电状态</span><span>{{ b.charge_label || '—' }}</span></div>
      <div class="kv">
        <span title="车体硬件急停按钮的状态，与网页上的「软急停」相互独立">硬急停（HES）</span>
        <span>
          <span class="pill" :class="b.hes === 1 ? 'pill-bad' : 'pill-ok'">
            <span class="status-dot" :class="b.hes === 1 ? 'bad pulse' : 'off'" />
            {{ b.hes === 1 ? '已触发' : '未触发' }}
          </span>
        </span>
      </div>
      <div class="kv"><span>休眠</span><span>{{ b.sleep_label || '—' }}</span></div>
      <div class="kv"><span title="车侧上报的辅助避障开关原始值（语义未随帧给出，仅按上报值展示）">辅助避障</span><span>{{ b.ooa ?? '—' }}</span></div>
      <div class="kv">
        <span>电源模式</span><span>{{ b.power_management === 1 ? '单电池' : '常规（双电池）' }}</span>
      </div>
      <div class="kv"><span>机型</span><span>{{ b.version || '—' }}</span></div>
    </div>
  </div>

  <div class="panel" :class="{ stale: isStale('device') }">
    <h3>
      设备状态
      <small>（1002/5 · 2Hz · BatteryList）</small>
    </h3>

    <!-- 逐块渲染：真机两块电池。旧版只显示 batteries[0]，而单电池模式下
         左电池全 0（=未安装），于是面板显示"电量 0 %"——看起来像"没有电量信息"
         （2026-10-16 修：逐块显示 + 明确标注未安装 + 低电量着色） -->
    <div v-if="batteries.length" class="stack">
      <div v-for="(bat, i) in batteries" :key="i" class="bat" :class="{ missing: !installed(bat) }">
        <div class="bat-top">
          <span class="bat-name">
            电池 {{ i + 1 }}<small>{{ i === 0 ? '（左）' : i === 1 ? '（右）' : '' }}</small>
          </span>
          <span class="bat-pct num" :class="levelClass(bat)">
            {{ installed(bat) ? Math.round(Number(bat.level)) + '%' : '未安装 / 无数据' }}
          </span>
        </div>
        <div class="bar">
          <div class="bar-fill" :class="levelClass(bat)" :style="{ width: barWidth(bat) }"></div>
        </div>
        <div class="bat-meta">
          <span>电压 <b class="num">{{ fmt(bat.voltage) }} V</b></span>
          <span>温度 <b class="num">{{ fmt(bat.temperature) }} ℃</b></span>
          <span>{{ bat.charging ? '充电中' : (installed(bat) ? '未充电' : '—') }}</span>
        </div>
      </div>
      <div class="bat-note">
        电源模式：<b>{{ powerModeLabel }}</b>
        <span v-if="missingCount">
          （{{ missingCount }} 块未安装/无数据 —— 单电池模式下属正常，不是故障）
        </span>
      </div>
    </div>

    <!-- 空状态：说明"为什么没有"，而不是留一块空白 -->
    <div v-else class="empty-state">
      <span class="empty-icon">∅</span>
      <span class="empty-title">暂无电池数据</span>
      <span class="empty-desc">尚未收到设备状态帧（1002/5）。若长时间为空，请检查实时链路与机器人供电。</span>
    </div>
  </div>

  <div class="panel" :class="{ stale: isStale('fault') }">
    <h3>
      异常状态
      <small>（1002/3）</small>
      <span class="spacer" />
      <span class="pill" :class="f.error_count ? 'pill-bad' : 'pill-ok'">
        <span class="status-dot" :class="f.error_count ? 'bad pulse' : 'ok'" />
        {{ f.error_count ? `${f.error_count} 条异常` : '无异常' }}
      </span>
    </h3>

    <div v-if="f.error_count">
      <table>
        <thead><tr><th>错误码</th><th>部件</th></tr></thead>
        <tbody>
          <tr v-for="(e, i) in f.errors" :key="i">
            <td class="mono">{{ e.code }}</td><td>{{ e.component }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty-state is-ok">
      <span class="empty-icon">✓</span>
      <span class="empty-title">未检测到异常</span>
      <span class="empty-desc">车侧未上报错误码。该结论只在数据新鲜（未置灰）时成立。</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  topic: { type: Function, required: true },
  isStale: { type: Function, required: true }
})

const b = computed(() => props.topic('basic'))
const f = computed(() => props.topic('fault'))

// ---- 运动状态的语义着色（只做展示映射，不改动任何判定逻辑）----
// 0 空闲 / 1 站立 / 2 软急停阻尼（告警）/ 3 开机阻尼 / 4 趴下 / 17 RL 控制
const motionPill = computed(() => {
  const m = b.value?.motion_state
  if (m == null) return 'pill-muted'
  if (Number(m) === 2) return 'pill-bad'
  if ([1, 17].includes(Number(m))) return 'pill-ok'
  if (Number(m) === 3) return 'pill-warn'
  return 'pill-muted'
})

// ---- 电池：逐块展示（真机 2 块）----
const batteries = computed(() => {
  const list = props.topic('device')?.batteries
  return Array.isArray(list) ? list : []
})

/**
 * 电池是否"在位"。判定：level 缺失 → 不在位；level 与 voltage **同时为 0** → 不在位。
 * 依据（2026-10-16 真机）：power_management=1（单电池模式）时左电池上报
 * level=0 / voltage=0 / 温度=0，而右电池 64% / 76V / 29.4℃——全 0 即未安装。
 */
function installed (bat) {
  if (!bat || bat.level == null) return false
  return !(Number(bat.level) === 0 && Number(bat.voltage) === 0)
}

function levelClass (bat) {
  if (!installed(bat)) return 'na'
  const l = Number(bat.level)
  if (l < 20) return 'low'      // 该充电了
  if (l < 50) return 'mid'
  return 'ok'
}

const barWidth = (bat) =>
  installed(bat) ? `${Math.max(0, Math.min(100, Number(bat.level)))}%` : '0%'

const fmt = (v) =>
  v == null || Number.isNaN(Number(v))
    ? '—'
    : String(Math.round(Number(v) * 10) / 10)

const missingCount = computed(() => batteries.value.filter((x) => !installed(x)).length)
const powerModeLabel = computed(() =>
  props.topic('basic')?.power_management === 1 ? '单电池' : '常规（双电池）')
</script>

<style scoped>
/* ---- 电池卡 ---- */
.bat {
  padding: var(--sp-2) var(--sp-3);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  transition: border-color var(--t);
}
.bat:hover { border-color: var(--line-strong); }
/* 未安装：整卡降饱和，避免被误读成"电量为 0" */
.bat.missing { border-style: dashed; opacity: 0.8; }

.bat-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--sp-2);
}

.bat-name { font-size: var(--fs-13); color: var(--text); }
.bat-name small { color: var(--muted); }

.bat-pct { font-size: var(--fs-17); font-weight: 600; }

.bar {
  height: 8px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: var(--r-pill);
  overflow: hidden;
  margin: var(--sp-2) 0 var(--sp-1);
}

.bar-fill {
  height: 100%;
  border-radius: var(--r-pill);
  transition: width 0.4s ease;
}
.bar-fill.ok { background: var(--ok); }
.bar-fill.mid { background: var(--warn); }
.bar-fill.low { background: var(--danger); }
.bar-fill.na { background: rgba(255, 255, 255, 0.16); }

.bat-pct.ok { color: var(--ok); }
.bat-pct.mid { color: var(--warn); }
.bat-pct.low { color: var(--danger); }
.bat-pct.na { color: var(--muted); font-size: var(--fs-13); font-weight: 400; }

.bat-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--muted);
}
.bat-meta b { color: var(--text); font-weight: 600; }

.bat-note {
  font-size: var(--fs-12);
  line-height: 1.6;
  color: var(--muted);
}
.bat-note b { color: var(--text); }

/* 无异常：用绿色调的空状态，明确"查过了、没问题" */
.empty-state.is-ok {
  color: var(--ok);
  background: var(--ok-soft);
  border: 1px solid var(--ok-line);
  border-style: solid;
}
.empty-state.is-ok .empty-title { color: var(--ok); }
.empty-state.is-ok .empty-desc { color: var(--muted); }
</style>
