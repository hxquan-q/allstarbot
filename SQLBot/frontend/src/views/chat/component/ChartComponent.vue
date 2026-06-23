<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import VChart from '@/views/chat/component/echarts/setup'
import { buildEChartsOption } from '@/views/chat/component/echarts/options.ts'
import { Table } from '@/views/chat/component/charts/Table.ts'
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
    recordId?: number
    echarts?: Record<string, any>
  }>(),
  {
    data: () => [],
    columns: () => [],
    x: () => [],
    y: () => [],
    series: () => [],
    multiQuotaName: undefined,
    showLabel: false,
    recordId: undefined,
    echarts: undefined,
  }
)

const chartId = computed(() => {
  return 'chart-component-' + params.id
})

const isTable = computed(() => params.type === 'table')

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

const option = computed(() =>
  isTable.value
    ? {}
    : buildEChartsOption({
        type: params.type,
        axis: axis.value,
        data: params.data,
        showLabel: params.showLabel,
        echarts: params.echarts,
      })
)

// --- table（S2）分支：沿用原 Table 类 ---
let tableInstance: BaseChart | undefined
const vchartRef = ref<any>(undefined)

function renderTable() {
  if (!isTable.value) {
    return
  }
  tableInstance?.destroy?.()
  tableInstance = new Table(chartId.value)
  tableInstance.showLabel = params.showLabel
  tableInstance.init(axis.value, params.data)
  tableInstance.render()
}

function renderChart() {
  if (isTable.value) {
    nextTick(renderTable)
  } else {
    vchartRef.value?.resize?.()
  }
}

function destroyChart() {
  if (tableInstance) {
    tableInstance.destroy?.()
    tableInstance = undefined
  }
  // VChart 随组件卸载自动 dispose
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

watch(
  [() => params.type, () => params.data, axis, () => params.showLabel],
  () => {
    if (isTable.value) {
      nextTick(renderTable)
    }
  },
  {
    deep: true,
  }
)

onMounted(() => {
  if (isTable.value) {
    nextTick(renderTable)
  }
})

onUnmounted(() => {
  destroyChart()
})
</script>

<template>
  <div class="chart-container-wrap">
    <VChart
      v-if="!isTable"
      ref="vchartRef"
      class="chart-container"
      :option="option"
      :autoresize="true"
      :update-options="{ notMerge: true }"
    />
    <div v-else :id="chartId" class="chart-container"></div>
  </div>
</template>

<style scoped lang="less">
.chart-container-wrap {
  position: relative;
  height: 100%;
  min-height: 320px;
  width: 100%;
}

.chart-container {
  height: 100%;
  min-height: 320px;
  width: 100%;
}
</style>
