<script setup>
/**
 * IMUChart.vue
 * 使用 ECharts 实时绘制 Roll / Pitch / Yaw 三条曲线，窗口 30 秒。
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  /** 历史数据数组：[{ t: ms, roll, pitch, yaw }] */
  history: { type: Array, default: () => [] }
})

const el = ref(null)
let chart = null

/** 组装 ECharts option */
function buildOption() {
  const data = props.history
  return {
    animation: false,
    grid: { left: 48, right: 16, top: 28, bottom: 28 },
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['Roll', 'Pitch', 'Yaw'],
      right: 8,
      top: 0,
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: '#6b7280' }
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#d8dee9' } },
      axisLabel: { fontSize: 10, color: '#94a3b8', hideOverlap: true },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      name: 'deg',
      nameTextStyle: { fontSize: 10, color: '#94a3b8' },
      axisLabel: { fontSize: 10, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#eef2f7' } }
    },
    series: [
      {
        name: 'Roll',
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#2563eb' },
        itemStyle: { color: '#2563eb' },
        data: data.map((p) => [p.t, p.roll])
      },
      {
        name: 'Pitch',
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#f59e0b' },
        itemStyle: { color: '#f59e0b' },
        data: data.map((p) => [p.t, p.pitch])
      },
      {
        name: 'Yaw',
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#16a34a' },
        itemStyle: { color: '#16a34a' },
        data: data.map((p) => [p.t, p.yaw])
      }
    ]
  }
}

/** 窗口尺寸自适应 */
function handleResize() {
  chart?.resize()
}

onMounted(() => {
  chart = echarts.init(el.value)
  chart.setOption(buildOption())
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})

// 数据更新时增量刷新；数据量较大时也走 setOption 全量覆盖，成本可控
watch(
  () => props.history,
  () => {
    if (!chart) return
    chart.setOption(buildOption(), { lazyUpdate: true })
  },
  { deep: false }
)
</script>

<template>
  <section class="card">
    <div class="card-title">
      <span>IMU Attitude</span>
      <span class="sub">最近 30 秒 · 实时曲线</span>
    </div>
    <div ref="el" class="chart" />
  </section>
</template>

<style scoped>
.chart {
  width: 100%;
  height: 260px;
}
</style>
