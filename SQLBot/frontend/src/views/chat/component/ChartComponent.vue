<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { getChartInstance } from '@/views/chat/component/index.ts'
import type { BaseChart, ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import { useEmitt } from '@/utils/useEmitt.ts'

const params = withDefaults(
  defineProps<{
    id: string | number
    type: string
    data?: Array<ChartData>
    columns?: Array<ChartAxis>
    x?: Array<ChartAxis>
    y?: Array<ChartAxis>
    series?: Array<ChartAxis>
    multiQuotaName?: string | undefined
    showLabel?: boolean
  }>(),
  {
    data: () => [],
    columns: () => [],
    x: () => [],
    y: () => [],
    series: () => [],
    multiQuotaName: undefined,
    showLabel: false,
  }
)

const chartId = computed(() => {
  return 'chart-component-' + params.id
})

const axis = computed(() => {
  const _list: Array<ChartAxis> = []
  params.columns.forEach((column) => {
    _list.push({ name: column.name, value: column.value })
  })
  params.x.forEach((column) => {
    _list.push({ name: column.name, value: column.value, type: 'x' })
  })
  params.y.forEach((column) => {
    _list.push({
      name: column.name,
      value: column.value,
      type: 'y',
      'multi-quota': column['multi-quota'],
    })
  })
  params.series.forEach((column) => {
    _list.push({ name: column.name, value: column.value, type: 'series' })
  })
  if (params.multiQuotaName) {
    _list.push({
      name: params.multiQuotaName,
      value: params.multiQuotaName,
      type: 'other-info',
      hidden: true,
    })
  }
  return _list
})

let chartInstance: BaseChart | undefined
let renderFrame: number | undefined
let resizeObserver: ResizeObserver | undefined
let lastObservedSize = ''

function cancelScheduledRender() {
  if (renderFrame !== undefined) {
    window.cancelAnimationFrame(renderFrame)
    renderFrame = undefined
  }
}

function renderChart() {
  destroyChart()
  const container = document.getElementById(chartId.value)
  const rect = container?.getBoundingClientRect()
  if (!container || !rect || rect.width <= 0 || rect.height <= 0) {
    return
  }

  chartInstance = getChartInstance(params.type, chartId.value)
  if (chartInstance) {
    try {
      chartInstance.showLabel = params.showLabel
      chartInstance.init(axis.value, params.data)
      chartInstance.render()
    } catch (error) {
      console.error('Failed to render chart:', error, {
        type: params.type,
        axis: axis.value,
        data: params.data,
      })
      destroyChart()
    }
  }
}

function scheduleRender() {
  cancelScheduledRender()
  renderFrame = window.requestAnimationFrame(() => {
    renderFrame = undefined
    renderChart()
  })
}

function observeContainer() {
  resizeObserver?.disconnect()
  const container = document.getElementById(chartId.value)
  const observeTarget = container?.parentElement ?? container
  if (!observeTarget) {
    return
  }

  resizeObserver = new ResizeObserver(([entry] = []) => {
    const size = entry?.contentRect
    if (!size || size.width <= 0 || size.height <= 0) {
      return
    }
    const nextSize = `${Math.round(size.width)}x${Math.round(size.height)}`
    if (nextSize === lastObservedSize && chartInstance) {
      return
    }
    lastObservedSize = nextSize
    scheduleRender()
  })
  resizeObserver.observe(observeTarget)
}

watch(
  [() => params.type, () => params.data, axis, () => params.showLabel],
  () => {
    scheduleRender()
  },
  {
    deep: true,
  }
)

function destroyChart() {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = undefined
  }
}

function getExcelData() {
  return {
    axis: axis.value,
    data: params.data,
  }
}

useEmitt({
  name: 'view-render-all',
  callback: renderChart,
})

useEmitt({
  name: `view-render-${params.id}`,
  callback: renderChart,
})

defineExpose({
  renderChart,
  destroyChart,
  getExcelData,
})

onMounted(() => {
  nextTick(() => {
    observeContainer()
    scheduleRender()
  })
})

onUnmounted(() => {
  cancelScheduledRender()
  resizeObserver?.disconnect()
  destroyChart()
})
</script>

<template>
  <div :id="chartId" class="chart-container"></div>
</template>

<style scoped lang="less">
.chart-container {
  height: 100%;
  min-height: 320px;
  width: 100%;
}
</style>
