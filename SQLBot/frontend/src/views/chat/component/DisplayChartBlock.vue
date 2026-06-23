<script setup lang="ts">
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import type { ChatMessage } from '@/api/chat.ts'
import { computed, nextTick, ref } from 'vue'
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'
import { useI18n } from 'vue-i18n'
import {
  canRenderChartConfig,
  isAxisItem,
  normalizeChartConfig,
  safeJsonParse,
  type ChartConfig,
} from '@/views/chat/component/chartConfig.ts'

const props = defineProps<{
  id?: number | string
  chartType: ChartTypes
  message: ChatMessage
  data: Array<{ [key: string]: any }>
  chartConfig?: ChartConfig
  loadingData?: boolean
  showLabel?: boolean
}>()

const { t } = useI18n()

const chartObject = computed<ChartConfig>(() => {
  if (props.chartConfig) {
    return props.chartConfig
  }
  if (props.message?.record?.chart) {
    return safeJsonParse<ChartConfig>(props.message.record.chart, {})
  }
  return {}
})

const normalizedChartObject = computed<ChartConfig>(() =>
  normalizeChartConfig(
    {
      ...chartObject.value,
      type: props.chartType,
    },
    props.data
  )
)

const canRender = computed(() => canRenderChartConfig(normalizedChartObject.value))

// 区分两种"渲染不出图"的情形：真的没数据 vs 有数据但当前图表配置无法渲染。
// 后者此前也显示"暂无数据"，具有误导性；这里改成明确提示并引导切换为表格。
const emptyDescription = computed(() => {
  if (props.loadingData) return t('chat.loading_data')
  if (!props.data || props.data.length === 0) return t('chat.no_data')
  return t('chat.chart_render_blocked') || '当前图表配置无法渲染，可切换为表格查看'
})

const xAxis = computed(() => {
  const x = normalizedChartObject.value?.axis?.x
  return isAxisItem(x) ? [x] : []
})
const yAxis = computed(() => {
  const y = normalizedChartObject.value?.axis?.y
  return (Array.isArray(y) ? y : y ? [y] : []).filter(isAxisItem)
})
const series = computed(() => {
  const series = normalizedChartObject.value?.axis?.series
  return isAxisItem(series) ? [series] : []
})

const columns = computed(() => (normalizedChartObject.value?.columns || []).filter(isAxisItem))

const multiQuotaName = computed(() => {
  return normalizedChartObject.value?.axis?.['multi-quota']?.name
})

const chartRef = ref()

function onTypeChange() {
  nextTick(() => {
    chartRef.value?.destroyChart()
    chartRef.value?.renderChart()
  })
}
function getViewInfo() {
  return {
    chart: {
      columns: columns.value,
      type: normalizedChartObject.value.type || props.chartType,
      xAxis: xAxis.value,
      yAxis: yAxis.value,
      series: series.value,
      title: normalizedChartObject.value.title,
    },
    data: { data: props.data },
  }
}
function getExcelData() {
  return chartRef.value?.getExcelData()
}

defineExpose({
  onTypeChange,
  getViewInfo,
  getExcelData,
})
</script>

<template>
  <div v-if="message.record?.chart" class="chart-base-container">
    <ChartComponent
      v-if="message.record.id && data?.length > 0 && canRender"
      :id="id ?? 'default_chat_id'"
      ref="chartRef"
      :type="normalizedChartObject.type || chartType"
      :columns="columns"
      :x="xAxis"
      :y="yAxis"
      :series="series"
      :data="data"
      :multi-quota-name="multiQuotaName"
      :show-label="showLabel"
      :record-id="message.record.id"
      :echarts="normalizedChartObject.echarts"
    />
    <el-empty v-else :description="emptyDescription" />
  </div>
</template>

<style scoped lang="less">
.chart-base-container {
  height: 100%;
  width: 100%;
  border-radius: 12px;
  background: rgba(224, 224, 226, 0.29);
}
</style>
