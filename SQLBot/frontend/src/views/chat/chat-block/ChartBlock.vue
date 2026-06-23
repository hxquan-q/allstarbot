<script setup lang="ts">
import type { ChatMessage } from '@/api/chat.ts'
import DisplayChartBlock from '@/views/chat/component/DisplayChartBlock.vue'
import ChartPopover from '@/views/chat/chat-block/ChartPopover.vue'
import { computed, ref, watch } from 'vue'
import { useClipboard } from '@vueuse/core'
import { concat } from 'lodash-es'
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'
import ICON_BAR from '@/assets/svg/chart/icon_bar_outlined.svg'
import ICON_COLUMN from '@/assets/svg/chart/icon_dashboard_outlined.svg'
import ICON_LINE from '@/assets/svg/chart/icon_chart-line.svg'
import ICON_PIE from '@/assets/svg/chart/icon_pie_outlined.svg'
import ICON_TABLE from '@/assets/svg/chart/icon_form_outlined.svg'
import icon_sql_outlined from '@/assets/svg/icon_sql_outlined.svg'
import icon_export_outlined from '@/assets/svg/icon_export_outlined.svg'
import icon_file_image_colorful from '@/assets/svg/icon_file-image_colorful.svg'
import icon_file_excel_colorful from '@/assets/svg/icon_file-excel_colorful.svg'
import icon_into_item_outlined from '@/assets/svg/icon_into-item_outlined.svg'
import icon_window_max_outlined from '@/assets/svg/icon_window-max_outlined.svg'
import icon_window_mini_outlined from '@/assets/svg/icon_window-mini_outlined.svg'
import icon_copy_outlined from '@/assets/svg/icon_copy_outlined.svg'
import ICON_STYLE from '@/assets/svg/icon_style-set_outlined.svg'
import { useI18n } from 'vue-i18n'
import SQLComponent from '@/views/chat/component/SQLComponent.vue'
import { useAssistantStore } from '@/stores/assistant'
import AddViewDashboard from '@/views/dashboard/common/AddViewDashboard.vue'
import html2canvas from 'html2canvas'
import { chatApi } from '@/api/chat'
import { useChatConfigStore } from '@/stores/chatConfig.ts'
import md from '@/utils/markdown'
import {
  canRenderChartConfig,
  isAxisItem,
  normalizeChartConfig,
  safeJsonParse,
  type ChartAxisItem,
  type ChartConfig,
} from '@/views/chat/component/chartConfig.ts'

const chatConfig = useChatConfigStore()
const showSQLBtn = chatConfig.getShowSQL

const props = withDefaults(
  defineProps<{
    recordId?: number
    message: ChatMessage
    isPredict?: boolean
    chatType?: ChartTypes
    initialChartConfig?: ChartConfig
    enlarge?: boolean
    loadingData?: boolean
  }>(),
  {
    recordId: undefined,
    isPredict: false,
    chatType: undefined,
    initialChartConfig: undefined,
    enlarge: false,
    loadingData: false,
  }
)

const { copy } = useClipboard({ legacy: true })
const loading = ref<boolean>(false)
const { t } = useI18n()
const addViewRef = ref<any>(null)
const emits = defineEmits(['exitFullScreen'])

const dataObject = computed<{
  fields?: Array<string>
  data?: Array<{ [key: string]: any }>
  limit?: number
  datasource?: number
  sql?: string
  profile?: Record<string, any>
  dimensions?: Array<any>
}>(() => {
  if (props.message?.record?.data) {
    if (typeof props.message?.record?.data === 'string') {
      return safeJsonParse(props.message.record.data, { fields: [], data: [] })
    } else {
      return props.message.record.data
    }
  }
  return { fields: [], data: [] }
})
const assistantStore = useAssistantStore()
const isCompletePage = computed(() => !assistantStore.getAssistant || assistantStore.getEmbedded)

const isAssistant = computed(() => assistantStore.getAssistant)

const chartId = computed(() => props.message?.record?.id + (props.enlarge ? '-fullscreen' : ''))

const data = computed(() => {
  if (props.isPredict) {
    let _list = []
    if (
      props.message?.record?.predict_data &&
      typeof props.message?.record?.predict_data === 'string'
    ) {
      if (
        props.message?.record?.predict_data.length > 0 &&
        props.message?.record?.predict_data.trim().startsWith('[') &&
        props.message?.record?.predict_data.trim().endsWith(']')
      ) {
        _list = safeJsonParse(props.message?.record?.predict_data, [])
      }
    } else {
      if (props.message?.record?.predict_data?.length > 0) {
        _list = props.message?.record?.predict_data
      }
    }
    if (_list.length == 0) {
      return _list
    }

    if (dataObject.value.data && dataObject.value.data?.length > 0) {
      return concat(dataObject.value.data, _list)
    }
    return _list
  } else {
    return dataObject.value.data || []
  }
})

const chartRef = ref()

const chartObject = computed<ChartConfig>(() => {
  if (props.message?.record?.chart) {
    return safeJsonParse<ChartConfig>(props.message.record.chart, {})
  }
  return {}
})

const baseChartObject = computed<ChartConfig>(() =>
  normalizeChartConfig(
    {
      ...chartObject.value,
      type: props.chatType ?? chartObject.value.type,
    },
    data.value,
    dataObject.value?.fields
  )
)

// 关键指标卡片数据
const keyMetrics = computed(() => {
  const profile = dataObject.value?.profile
  if (profile && Array.isArray(profile.key_metrics)) {
    return profile.key_metrics
  }
  return []
})

// 多维度分析结果
const dimensionResults = computed(() => {
  if (props.message?.record?.dimensions && Array.isArray(props.message.record.dimensions)) {
    return props.message.record.dimensions
  }
  if (dataObject.value?.dimensions && Array.isArray(dataObject.value.dimensions)) {
    return dataObject.value.dimensions
  }
  return []
})

const expandedDimension = ref<number | undefined>(undefined)

function toggleDimension(idx: number) {
  expandedDimension.value = expandedDimension.value === idx ? undefined : idx
}

function formatMetricValue(value: any): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'number') {
    if (Math.abs(value) >= 1e8) {
      return (value / 1e8).toFixed(2) + '亿'
    }
    if (Math.abs(value) >= 1e4) {
      return (value / 1e4).toFixed(2) + '万'
    }
    if (Number.isInteger(value)) {
      return value.toLocaleString()
    }
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
  return String(value)
}

const currentChartType = ref<ChartTypes | undefined>(
  (props.chatType ?? baseChartObject.value.type ?? 'table') as ChartTypes
)
const selectedChartConfig = ref<ChartConfig | undefined>(props.initialChartConfig)

function tableColumnsFromData(): Array<ChartAxisItem> {
  const fields = dataObject.value?.fields || []
  return fields.map((field) => ({ name: field, value: field }))
}

function completeChartConfig(config?: ChartConfig): ChartConfig {
  const merged = normalizeChartConfig(
    {
      ...baseChartObject.value,
      ...(config || {}),
    },
    data.value,
    dataObject.value?.fields
  )
  if (!config && currentChartType.value) {
    merged.type = currentChartType.value
  }
  const completed = normalizeChartConfig(merged, data.value, dataObject.value?.fields)
  if (completed.type === 'table' && (!completed.columns || completed.columns.length === 0)) {
    completed.columns = tableColumnsFromData()
  }
  return completed
}

const currentChartObject = computed<ChartConfig>(() => {
  return completeChartConfig(selectedChartConfig.value)
})

const currentColumns = computed(() => (currentChartObject.value.columns || []).filter(isAxisItem))

const chartInsights = computed(() => {
  return Array.isArray(currentChartObject.value?.insights) ? currentChartObject.value.insights : []
})

// 图文并茂：图表的文字解读（summary）
const chartSummary = computed(() => {
  const s = currentChartObject.value?.summary
  return typeof s === 'string' ? s.trim() : ''
})

// 轻度折叠：长报告默认只展示"总论 + 首个分层段"，避免文字分析把整条回答拉得过长；
// 用户点击"展开全文"查看完整分层/行动建议。切到新回答时自动回到折叠态。
const SUMMARY_KEEP_SECTIONS = 2
const summaryExpanded = ref(false)
const summarySections = computed(() => {
  const text = chartSummary.value
  if (!text) return []
  // 按行首 "## " 二级标题切分（不含 ### 三级），保留分隔符
  return text.split(/(?=^## )/m).filter((part) => part.trim().length > 0)
})
const summaryIsLong = computed(() => summarySections.value.length > SUMMARY_KEEP_SECTIONS)
const displaySummary = computed(() => {
  if (!summaryIsLong.value || summaryExpanded.value) return chartSummary.value
  return summarySections.value.slice(0, SUMMARY_KEEP_SECTIONS).join('').trim()
})
const displaySummaryHtml = computed(() => {
  if (!displaySummary.value) return ''
  try {
    return md.render(displaySummary.value)
  } catch (e) {
    return displaySummary.value
  }
})
watch(chartSummary, () => {
  summaryExpanded.value = false
})

const chartAlternatives = computed(() => {
  return Array.isArray(currentChartObject.value?.alternatives)
    ? currentChartObject.value.alternatives.filter((item) => item?.type)
    : []
})

function completeFlatChartConfig(config: ChartConfig): ChartConfig {
  const completed = normalizeChartConfig(config, data.value, dataObject.value?.fields)
  if (completed.type === 'table' && (!completed.columns || completed.columns.length === 0)) {
    completed.columns = tableColumnsFromData()
  }
  return completed
}

const flatAlternativeCharts = computed(() =>
  chartAlternatives.value
    .map((item, idx) => ({
      index: idx,
      config: completeFlatChartConfig(item),
      raw: item,
    }))
    .filter((item) => canRenderChartConfig(item.config))
)

const chartType = computed<ChartTypes>({
  get() {
    if (currentChartType.value) {
      return currentChartType.value
    }
    return (props.chatType ?? currentChartObject.value.type ?? 'table') as ChartTypes
  },
  set(v) {
    currentChartType.value = v
  },
})

const renderChartType = computed<ChartTypes>(() => (currentChartObject.value.type || chartType.value) as ChartTypes)

const chartTypeList = computed(() => {
  const _list = []
  if (baseChartObject.value) {
    switch (baseChartObject.value.type) {
      case 'table':
        break
      case 'column':
      case 'bar':
      case 'line':
      case 'area':
      case 'scatter':
        _list.push({
          value: 'column',
          name: t('chat.chart_type.column'),
          icon: ICON_COLUMN,
        })
        _list.push({
          value: 'bar',
          name: t('chat.chart_type.bar'),
          icon: ICON_BAR,
        })
        _list.push({
          value: 'line',
          name: t('chat.chart_type.line'),
          icon: ICON_LINE,
        })
        _list.push({
          value: 'area',
          name: t('chat.chart_type.area'),
          icon: ICON_LINE,
        })
        _list.push({
          value: 'scatter',
          name: t('chat.chart_type.scatter'),
          icon: ICON_COLUMN,
        })
        break
      case 'pie':
        _list.push({
          value: 'pie',
          name: t('chat.chart_type.pie'),
          icon: ICON_PIE,
        })
    }
  }

  return _list
})

function changeTable() {
  onTypeChange('table')
}

function onTypeChange(val: any) {
  chartType.value = val
  selectedChartConfig.value = completeChartConfig()
  chartRef.value?.onTypeChange()
}

function reloadChart() {
  chartRef.value?.onTypeChange()
}

function chartTypeName(type?: ChartTypes | string) {
  return type ? t(`chat.chart_type.${type}`) : t('chat.type')
}

function chartConfigType(config?: ChartConfig): ChartTypes {
  return (config?.type || 'table') as ChartTypes
}

function renderMarkdownText(value?: string) {
  if (!value) return ''
  try {
    return md.render(value)
  } catch (e) {
    return value
  }
}

function alternativeInsights(config: ChartConfig) {
  return Array.isArray(config.insights) ? config.insights : []
}

const dialogVisible = ref(false)

function setHiddenSidebarBtnZIndex(value: string) {
  const sidebarBtns = document.querySelectorAll('.hidden-sidebar-btn')
  sidebarBtns.forEach((btn) => {
    ;(btn as HTMLElement).style.zIndex = value
  })
}

function openFullScreen() {
  setHiddenSidebarBtnZIndex('0')
  dialogVisible.value = true
}

function closeFullScreen() {
  emits('exitFullScreen')
}

function onExitFullScreen() {
  dialogVisible.value = false
  setHiddenSidebarBtnZIndex('11')
}

const sqlShow = ref(false)

function showSql() {
  sqlShow.value = true
}

const showLabel = ref(false)

function addToDashboard() {
  const recordeInfo = {
    id: '1-1',
    data: {
      data: data.value,
    },
    sql: props.message?.record?.sql,
    datasource: props.message?.record?.datasource,
    chart: {},
  }
  const chartBaseInfo = currentChartObject.value
  if (chartBaseInfo) {
    let yAxis: Array<ChartAxisItem & { 'multi-quota'?: boolean }> = []
    const axis = chartBaseInfo?.axis
    if (!axis?.y) {
      yAxis = []
    } else {
      const y = axis.y
      const rawMultiQuotaValues = axis['multi-quota']?.value
      const multiQuotaValues = Array.isArray(rawMultiQuotaValues)
        ? rawMultiQuotaValues
        : rawMultiQuotaValues
          ? [rawMultiQuotaValues]
          : []

      // 统一处理为数组
      const yArray = (Array.isArray(y) ? y : [y]).filter(isAxisItem)

      // 标记 multi-quota
      yAxis = yArray.map((item) => ({
        ...item,
        'multi-quota': multiQuotaValues.includes(item.value),
      }))
    }

    recordeInfo['chart'] = {
      type: renderChartType.value,
      title: chartBaseInfo?.title,
      columns: currentColumns.value,
      xAxis: isAxisItem(axis?.x) ? [axis?.x] : [],
      yAxis: yAxis,
      series: isAxisItem(axis?.series) ? [axis?.series] : [],
      multiQuotaName: axis?.['multi-quota']?.name,
    }
  }

  addViewRef.value?.optInit(recordeInfo)
}

function copyText() {
  if (props.message?.record?.sql) {
    copy(props.message.record.sql).then(() => {
      ElMessage.success(t('embedded.copy_successful'))
    })
  }
}

const exportRef = ref()

function exportToExcel() {
  if (chartRef.value && props.recordId) {
    loading.value = true
    chatApi
      .export2Excel(props.recordId, props.message?.record?.chat_id || 0)
      .then((res) => {
        const blob = new Blob([res], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = `${currentChartObject.value.title ?? 'Excel'}.xlsx`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      })
      .catch(async (error) => {
        if (error.response) {
          try {
            let text = await error.response.data.text()
            try {
              text = JSON.parse(text)
            } finally {
              ElMessage({
                message: text,
                type: 'error',
                showClose: true,
              })
            }
          } catch (e) {
            console.error('Error processing error response:', e)
          }
        } else {
          console.error('Other error:', error)
          ElMessage({
            message: error,
            type: 'error',
            showClose: true,
          })
        }
      })
      .finally(() => {
        loading.value = false
      })
    exportRef.value?.hide()
  }
}

function exportToImage() {
  const obj = document.getElementById('chart-component-' + chartId.value)
  if (obj) {
    html2canvas(obj).then((canvas) => {
      canvas.toBlob(function (blob) {
        if (blob) {
          const link = document.createElement('a')
          link.download = (currentChartObject.value.title ?? 'chart') + '.png' // Specify filename
          link.href = URL.createObjectURL(blob)
          document.body.appendChild(link) // Append to body to make it clickable
          link.click() // Programmatically click the link
          document.body.removeChild(link) // Clean up
          URL.revokeObjectURL(link.href) // Release the object URL
        }
      }, 'image/png')
    })
  }
  exportRef.value?.hide()
}

defineExpose({
  reloadChart,
})

watch(
  () => props.message?.record?.chart,
  (val) => {
      if (val) {
      selectedChartConfig.value = props.initialChartConfig
      currentChartType.value = (props.chatType ?? baseChartObject.value.type ?? 'table') as ChartTypes
    }
  }
)
</script>

<template>
  <div
    v-if="
      !message.isTyping &&
      ((!isPredict && (message?.record?.sql || message?.record?.chart)) ||
        (isPredict && message?.record?.chart && data.length > 0))
    "
    v-loading.fullscreen.lock="loading"
    class="chart-component-container"
    :class="{ 'full-screen': enlarge }"
  >
    <div class="header-bar">
      <div class="title">
        {{ currentChartObject.title }}
      </div>
      <div class="buttons-bar">
        <div class="chart-select-container">
          <el-tooltip effect="dark" :offset="8" :content="t('chat.type')" placement="top">
            <ChartPopover
              v-if="chartTypeList.length > 0"
              :chart-type-list="chartTypeList"
              :chart-type="renderChartType"
              :title="t('chat.type')"
              @type-change="onTypeChange"
            ></ChartPopover>
          </el-tooltip>

          <el-tooltip
            effect="dark"
            :offset="8"
            :content="t('chat.chart_type.table')"
            placement="top"
          >
            <el-button
              class="tool-btn"
              :class="{ 'chart-active': renderChartType === 'table' }"
              text
              @click="changeTable"
            >
              <el-icon size="16">
                <ICON_TABLE />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>

        <div v-if="renderChartType !== 'table'" class="chart-select-container">
          <el-tooltip
            effect="dark"
            :offset="8"
            :content="showLabel ? t('chat.hide_label') : t('chat.show_label')"
            placement="top"
          >
            <el-button
              class="tool-btn"
              :class="{ 'chart-active': showLabel }"
              text
              @click="showLabel = !showLabel"
            >
              <el-icon size="16">
                <ICON_STYLE />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>

        <div v-if="message?.record?.sql && showSQLBtn">
          <el-tooltip effect="dark" :offset="8" :content="t('chat.show_sql')" placement="top">
            <el-button class="tool-btn" text @click="showSql">
              <el-icon size="16">
                <icon_sql_outlined />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <div v-if="message?.record?.chart">
          <el-popover
            ref="exportRef"
            trigger="click"
            popper-class="export_to_select"
            placement="bottom"
          >
            <template #reference>
              <div>
                <el-tooltip
                  effect="dark"
                  :offset="8"
                  :content="t('chat.export_to')"
                  placement="top"
                >
                  <el-button class="tool-btn" text>
                    <el-icon size="16">
                      <icon_export_outlined />
                    </el-icon>
                  </el-button>
                </el-tooltip>
              </div>
            </template>
            <div class="popover">
              <div class="popover-content">
                <div class="title">{{ t('chat.export_to') }}</div>
                <div class="popover-item" @click="exportToExcel">
                  <el-icon size="16">
                    <icon_file_excel_colorful />
                  </el-icon>
                  <div class="model-name">{{ t('chat.excel') }}</div>
                </div>
                <div
                  v-if="renderChartType !== 'table'"
                  class="popover-item"
                  @click="exportToImage"
                >
                  <el-icon size="16">
                    <icon_file_image_colorful />
                  </el-icon>
                  <div class="model-name">{{ t('chat.picture') }}</div>
                </div>
              </div>
            </div>
          </el-popover>
        </div>
        <div v-if="message?.record?.chart && !isAssistant">
          <el-tooltip effect="dark" :content="t('chat.add_to_dashboard')" placement="top">
            <el-button class="tool-btn" text @click="addToDashboard">
              <el-icon size="16">
                <icon_into_item_outlined />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <div class="divider" />
        <div v-if="!enlarge">
          <el-tooltip
            effect="dark"
            :offset="8"
            :content="!isCompletePage ? $t('common.zoom_in') : t('chat.full_screen')"
            placement="top"
          >
            <el-button class="tool-btn" text @click="openFullScreen">
              <el-icon size="16">
                <icon_window_max_outlined />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <div v-else>
          <el-tooltip
            effect="dark"
            :offset="8"
            :content="!isCompletePage ? $t('common.zoom_out') : t('chat.exit_full_screen')"
            placement="top"
          >
            <el-button class="tool-btn" text @click="closeFullScreen">
              <el-icon size="16">
                <icon_window_mini_outlined />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </div>
    </div>

    <template v-if="message?.record?.chart">
      <!-- 图文并茂：文字解读 summary -->
      <div
        v-if="chartSummary"
        class="chart-summary-panel markdown-body"
        v-dompurify-html="displaySummaryHtml"
      ></div>
      <div v-if="chartSummary && summaryIsLong" class="summary-toggle-row">
        <span class="summary-toggle-btn" @click="summaryExpanded = !summaryExpanded">
          {{ summaryExpanded ? t('chat.collapse') || '收起' : t('chat.expand') || '展开全文' }}
          <span class="toggle-arrow" :class="{ expanded: summaryExpanded }">▾</span>
        </span>
      </div>
      <div class="chart-block">
        <DisplayChartBlock
          :id="chartId"
          ref="chartRef"
          :chart-type="renderChartType"
          :message="message"
          :chart-config="currentChartObject"
          :data="data"
          :loading-data="loadingData"
          :show-label="showLabel"
        />
      </div>
      <!-- 关键指标卡片 -->
      <div v-if="keyMetrics.length > 0" class="key-metrics-panel">
        <div
          v-for="(metric, idx) in keyMetrics"
          :key="'metric-' + idx"
          class="metric-card"
        >
          <div class="metric-name">{{ metric.name }}</div>
          <div class="metric-value">{{ formatMetricValue(metric.sum ?? metric.avg) }}</div>
          <div class="metric-details">
            <span v-if="metric.avg !== undefined && metric.avg !== null">均值: {{ formatMetricValue(metric.avg) }}</span>
            <span v-if="metric.min !== undefined && metric.min !== null"> | 最小: {{ formatMetricValue(metric.min) }}</span>
            <span v-if="metric.max !== undefined && metric.max !== null"> | 最大: {{ formatMetricValue(metric.max) }}</span>
          </div>
        </div>
      </div>
      <div v-if="dataObject.limit" class="over-limit-hint">
        {{ t('chat.data_over_limit', [dataObject.limit]) }}
      </div>
      <!-- 多维度分析面板 -->
      <div v-if="dimensionResults.length > 0" class="dimension-analysis-panel">
        <div class="analysis-title">{{ t('chat.dimension_analysis') || '多维度分析' }}</div>
        <div class="dimension-list">
          <div
            v-for="(dim, idx) in dimensionResults"
            :key="'dim-' + idx"
            class="dimension-item"
            :class="{ expanded: expandedDimension === idx }"
          >
            <div class="dimension-header" @click="toggleDimension(idx)">
              <span class="dimension-type-tag">{{ dim.dimension_title || dim.dimension_type }}</span>
              <span class="dimension-insight">{{ dim.insight }}</span>
              <span class="dimension-toggle">{{ expandedDimension === idx ? '▾' : '▸' }}</span>
            </div>
            <div v-if="expandedDimension === idx && dim.details" class="dimension-details">
              <ul>
                <li v-for="(detail, dIdx) in dim.details" :key="'detail-' + dIdx">
                  {{ detail }}
                </li>
              </ul>
              <div v-if="dim.chart_config" class="dimension-chart-hint">
                推荐图表: <span class="chart-type-badge">{{ chartTypeName(dim.chart_config.type) }}</span>
                {{ dim.chart_config.title }}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-if="chartInsights.length" class="chart-analysis-panel">
        <div v-if="chartInsights.length" class="analysis-section">
          <div class="analysis-title">{{ t('chat.chart_insights') }}</div>
          <ul class="analysis-list">
            <li v-for="(item, idx) in chartInsights" :key="'insight-' + idx">
              {{ item }}
            </li>
          </ul>
        </div>
      </div>
      <div v-if="flatAlternativeCharts.length" class="flat-alternatives-panel">
        <div class="analysis-title">{{ t('chat.chart_alternatives') }}</div>
        <div class="flat-alternative-list">
          <section
            v-for="item in flatAlternativeCharts"
            :key="'flat-alternative-' + item.index"
            class="flat-alternative-card"
          >
            <div class="flat-alternative-header">
              <span class="alternative-type">{{ chartTypeName(item.config.type) }}</span>
              <span class="flat-alternative-title">
                {{ item.config.title || item.raw.title || `${t('chat.chart_alternatives')} ${item.index + 1}` }}
              </span>
            </div>
            <div v-if="item.config.reason || item.raw.reason" class="flat-alternative-reason">
              {{ item.config.reason || item.raw.reason }}
            </div>
            <div
              v-if="item.config.summary"
              class="flat-alternative-summary markdown-body"
              v-dompurify-html="renderMarkdownText(item.config.summary)"
            ></div>
            <div class="flat-alternative-chart">
              <DisplayChartBlock
                :id="`${chartId}-alternative-${item.index}`"
                :chart-type="chartConfigType(item.config)"
                :message="message"
                :chart-config="item.config"
                :data="data"
                :loading-data="loadingData"
                :show-label="showLabel"
              />
            </div>
            <ul v-if="alternativeInsights(item.config).length" class="analysis-list compact">
              <li
                v-for="(insight, insightIdx) in alternativeInsights(item.config)"
                :key="'alternative-insight-' + item.index + '-' + insightIdx"
              >
                {{ insight }}
              </li>
            </ul>
          </section>
        </div>
      </div>
    </template>

    <AddViewDashboard ref="addViewRef"></AddViewDashboard>
    <el-dialog
      v-if="!enlarge"
      v-model="dialogVisible"
      fullscreen
      :show-close="false"
      class="chart-fullscreen-dialog"
      header-class="chart-fullscreen-dialog-header"
      body-class="chart-fullscreen-dialog-body"
    >
      <ChartBlock
        v-if="dialogVisible"
        :message="message"
        :record-id="recordId"
        :is-predict="isPredict"
        :chat-type="renderChartType"
        :initial-chart-config="currentChartObject"
        :loading-data="loadingData"
        enlarge
        @exit-full-screen="onExitFullScreen"
      />
    </el-dialog>

    <el-drawer
      v-model="sqlShow"
      :size="!isCompletePage ? '100%' : '600px'"
      :title="t('chat.show_sql')"
      direction="rtl"
      body-class="chart-sql-drawer-body"
    >
      <div class="sql-block">
        <SQLComponent
          v-if="message.record?.sql"
          :sql="message.record?.sql"
          style="margin-top: 12px"
        />
        <el-button v-if="message.record?.sql" circle class="input-icon" @click="copyText">
          <el-icon size="16">
            <icon_copy_outlined />
          </el-icon>
        </el-button>
      </div>
    </el-drawer>
  </div>
</template>

<style lang="less">
.chart-fullscreen-dialog {
  padding: 0;
}

.chart-fullscreen-dialog-header {
  display: none;
}

.chart-fullscreen-dialog-body {
  padding: 0;
  height: 100%;
}

.chart-sql-drawer-body {
  padding: 24px;
}

.export_to_select.export_to_select {
  padding: 4px 0;
  width: 120px !important;
  min-width: 120px !important;
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border: 1px solid #dee0e3;

  .popover {
    .popover-content {
      padding: 0 4px;
      max-height: 300px;
      overflow-y: auto;

      .title {
        width: 100%;
        height: 32px;
        margin-bottom: 2px;
        display: flex;
        align-items: center;
        padding-left: 8px;
        color: #8f959e;
      }
    }

    .popover-item {
      height: 32px;
      display: flex;
      align-items: center;
      padding-left: 12px;
      padding-right: 8px;
      margin-bottom: 2px;
      position: relative;
      border-radius: 6px;
      cursor: pointer;

      &:last-child {
        margin-bottom: 0;
      }

      &:hover {
        background: #1f23291a;
      }

      .model-name {
        margin-left: 8px;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        max-width: 220px;
      }

      .done {
        margin-left: auto;
        display: none;
      }

      &.isActive {
        color: var(--ed-color-primary);

        .done {
          display: block;
        }
      }
    }
  }
}
</style>
<style scoped lang="less">
.chart-component-container {
  width: 100%;
  padding: 20px;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(222, 224, 227, 1);
  border-radius: 12px;

  &.full-screen {
    border: unset;
    border-radius: unset;
    padding: 0;
    height: 100%;
    overflow-y: auto;

    .header-bar {
      border-bottom: 1px solid rgba(31, 35, 41, 0.15);
      height: 55px;
      padding: 16px 24px;
    }

    .chart-block {
      flex: none;
      margin: 20px;
      padding: 0;
      height: min(560px, calc(100vh - 180px));
      min-height: 360px;
    }

    .chart-summary-panel,
    .over-limit-hint,
    .dimension-analysis-panel,
    .chart-analysis-panel,
    .flat-alternatives-panel {
      margin: 20px 20px 0;
    }

    .key-metrics-panel {
      margin: 20px 20px 0;
    }
  }

  .header-bar {
    height: 32px;
    display: flex;

    align-items: center;
    flex-direction: row;
    gap: 16px;

    .tool-btn {
      width: 24px;
      height: 24px;

      font-size: 16px;
      font-weight: 400;
      line-height: 24px;
      border-radius: 6px;
      color: rgba(100, 106, 115, 1);

      .tool-btn-inner {
        display: flex;
        flex-direction: row;
        align-items: center;
      }

      &:hover {
        background: rgba(31, 35, 41, 0.1);
      }

      &:active {
        background: rgba(31, 35, 41, 0.1);
      }
    }

    .chart-active {
      background: var(--ed-color-primary-1a, rgba(28, 186, 144, 0.1));
      color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      border-radius: 6px;

      :deep(.ed-select__wrapper) {
        background: transparent;
      }

      :deep(.ed-select__input) {
        color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      }

      :deep(.ed-select__placeholder) {
        color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      }

      :deep(.ed-select__caret) {
        color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      }
    }

    .title {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;

      color: rgba(31, 35, 41, 1);
      font-weight: 500;
      font-size: 16px;
      line-height: 24px;
    }

    .buttons-bar {
      display: flex;
      flex-direction: row;
      align-items: center;

      gap: 16px;

      .divider {
        width: 1px;
        height: 16px;
        border-left: 1px solid rgba(31, 35, 41, 0.15);
      }
    }

    .chart-select-container {
      padding: 3px;
      display: flex;
      flex-direction: row;
      gap: 4px;
      border-radius: 6px;

      border: 1px solid rgba(217, 220, 223, 1);

      .chart-select {
        min-width: 40px;
        width: 40px;
        height: 24px;

        :deep(.ed-select__wrapper) {
          padding: 4px;
          min-height: 24px;
          box-shadow: unset;
          border-radius: 6px;

          &:hover {
            background: rgba(31, 35, 41, 0.1);
          }

          &:active {
            background: rgba(31, 35, 41, 0.1);
          }
        }

        :deep(.ed-select__caret) {
          font-size: 12px !important;
        }
      }
    }
  }

  .chart-block {
    height: 352px;
    width: 100%;

    margin-top: 20px;
  }

  .chart-summary-panel {
    margin-top: 16px;
    padding: 16px 18px;
    border-radius: 8px;
    border-left: 3px solid var(--ed-color-primary, rgba(28, 186, 144, 1));
    background: linear-gradient(90deg, rgba(91, 143, 249, 0.05) 0%, rgba(255, 255, 255, 0) 60%);
    font-size: 14px;
    line-height: 22px;
    color: rgba(31, 35, 41, 1);

    :deep(h2) {
      margin: 14px 0 6px 0;
      padding-bottom: 4px;
      font-size: 15px;
      font-weight: 600;
      line-height: 22px;
      border-bottom: 1px solid rgba(31, 35, 41, 0.08);
      color: rgba(31, 35, 41, 1);
      &:first-child {
        margin-top: 0;
      }
    }

    :deep(h3) {
      margin: 8px 0 4px 0;
      font-size: 14px;
      font-weight: 600;
      color: rgba(78, 84, 93, 1);
    }

    :deep(p) {
      margin: 0 0 6px 0;
      &:last-child {
        margin-bottom: 0;
      }
    }

    :deep(ul),
    :deep(ol) {
      margin: 4px 0;
      padding-left: 20px;
    }

    :deep(li) {
      margin: 2px 0;
    }

    :deep(strong) {
      color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      font-weight: 600;
    }

    :deep(table) {
      width: 100%;
      border-collapse: collapse;
      margin: 6px 0;
      font-size: 13px;
      th,
      td {
        border: 1px solid rgba(31, 35, 41, 0.12);
        padding: 4px 8px;
        text-align: left;
      }
      th {
        background: rgba(31, 35, 41, 0.04);
        font-weight: 600;
      }
    }

    :deep(code) {
      padding: 1px 4px;
      border-radius: 3px;
      background: rgba(31, 35, 41, 0.06);
      font-size: 13px;
    }

    :deep(hr) {
      border: none;
      border-top: 1px solid rgba(31, 35, 41, 0.08);
      margin: 10px 0;
    }
  }
  .summary-toggle-row {
    display: flex;
    justify-content: center;
    margin-top: 4px;
  }

  .summary-toggle-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    font-size: 12px;
    line-height: 18px;
    color: var(--ed-color-primary, rgba(28, 186, 144, 1));
    cursor: pointer;
    user-select: none;
    border-radius: 6px;
    transition: background 0.15s ease;

    &:hover {
      background: rgba(28, 186, 144, 0.08);
    }

    .toggle-arrow {
      display: inline-block;
      transition: transform 0.18s ease;

      &.expanded {
        transform: rotate(180deg);
      }
    }
  }

  .over-limit-hint {
    min-height: 24px;
    line-height: 24px;
    font-size: 14px;
  }

  .key-metrics-panel {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 20px;
    padding: 0 4px;

    .metric-card {
      flex: 1;
      min-width: 140px;
      max-width: 220px;
      padding: 12px;
      border-radius: 8px;
      background: linear-gradient(135deg, rgba(91, 143, 249, 0.06) 0%, rgba(90, 216, 166, 0.06) 100%);
      border: 1px solid rgba(91, 143, 249, 0.15);

      .metric-name {
        font-size: 12px;
        color: rgba(100, 106, 115, 1);
        line-height: 18px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .metric-value {
        font-size: 20px;
        font-weight: 600;
        color: rgba(31, 35, 41, 1);
        line-height: 28px;
        margin-top: 4px;
      }

      .metric-details {
        font-size: 11px;
        color: rgba(100, 106, 115, 1);
        line-height: 16px;
        margin-top: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }
  }

  .dimension-analysis-panel {
    margin-top: 20px;
    padding: 12px;
    border: 1px solid rgba(222, 224, 227, 1);
    border-radius: 8px;
    background: rgba(247, 248, 250, 1);

    > .analysis-title {
      margin-bottom: 8px;
      color: rgba(31, 35, 41, 1);
      font-size: 13px;
      font-weight: 600;
      line-height: 20px;
    }

    .dimension-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .dimension-item {
      border: 1px solid rgba(222, 224, 227, 1);
      border-radius: 6px;
      background: #fff;
      overflow: hidden;
      transition: border-color 0.2s;

      &.expanded {
        border-color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      }

      .dimension-header {
        padding: 8px 12px;
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        font-size: 13px;
        line-height: 20px;

        &:hover {
          background: rgba(31, 35, 41, 0.03);
        }
      }

      .dimension-type-tag {
        padding: 1px 6px;
        border-radius: 4px;
        color: var(--ed-color-primary, rgba(28, 186, 144, 1));
        background: var(--ed-color-primary-1a, rgba(28, 186, 144, 0.1));
        font-size: 12px;
        white-space: nowrap;
      }

      .dimension-insight {
        flex: 1;
        color: rgba(78, 84, 93, 1);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .dimension-toggle {
        color: rgba(100, 106, 115, 1);
        font-size: 12px;
      }

      .dimension-details {
        padding: 8px 12px 12px;
        border-top: 1px solid rgba(222, 224, 227, 0.6);

        ul {
          margin: 0;
          padding-left: 18px;
          color: rgba(78, 84, 93, 1);
          font-size: 13px;
          line-height: 22px;
        }

        .dimension-chart-hint {
          margin-top: 8px;
          font-size: 12px;
          color: rgba(100, 106, 115, 1);

          .chart-type-badge {
            padding: 1px 4px;
            border-radius: 3px;
            background: rgba(91, 143, 249, 0.1);
            color: #5B8FF9;
          }
        }
      }
    }
  }

  .chart-analysis-panel {
    margin-top: 20px;
    padding: 12px;
    border: 1px solid rgba(222, 224, 227, 1);
    border-radius: 8px;
    background: rgba(247, 248, 250, 1);

    .analysis-section + .analysis-section {
      margin-top: 10px;
    }

    .analysis-title {
      margin-bottom: 6px;
      color: rgba(31, 35, 41, 1);
      font-size: 13px;
      font-weight: 600;
      line-height: 20px;
    }

    .analysis-list {
      margin: 0;
      padding-left: 18px;
      color: rgba(78, 84, 93, 1);
      font-size: 13px;
      line-height: 20px;
    }
  }

  .flat-alternatives-panel {
    margin-top: 20px;
    padding: 12px;
    border: 1px solid rgba(222, 224, 227, 1);
    border-radius: 8px;
    background: rgba(247, 248, 250, 1);

    > .analysis-title {
      margin-bottom: 10px;
      color: rgba(31, 35, 41, 1);
      font-size: 13px;
      font-weight: 600;
      line-height: 20px;
    }

    .flat-alternative-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .alternative-type {
      flex: none;
      min-width: 48px;
      padding: 1px 6px;
      border-radius: 4px;
      color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      background: var(--ed-color-primary-1a, rgba(28, 186, 144, 0.1));
      text-align: center;
    }

    .flat-alternative-card {
      width: 100%;
      min-width: 0;
      padding: 12px;
      border: 1px solid rgba(222, 224, 227, 1);
      border-radius: 8px;
      background: #fff;
    }

    .flat-alternative-header {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }

    .flat-alternative-title {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: rgba(31, 35, 41, 1);
      font-weight: 500;
      font-size: 14px;
      line-height: 22px;
    }

    .flat-alternative-reason {
      margin-top: 6px;
      color: rgba(100, 106, 115, 1);
      font-size: 13px;
      line-height: 20px;
    }

    .flat-alternative-summary {
      margin-top: 8px;
      padding: 10px 12px;
      border-radius: 6px;
      background: rgba(31, 35, 41, 0.03);
      color: rgba(78, 84, 93, 1);
      font-size: 13px;
      line-height: 20px;

      :deep(p) {
        margin: 0 0 6px 0;
        &:last-child {
          margin-bottom: 0;
        }
      }

      :deep(ul),
      :deep(ol) {
        margin: 4px 0;
        padding-left: 18px;
      }

      :deep(strong) {
        color: var(--ed-color-primary, rgba(28, 186, 144, 1));
        font-weight: 600;
      }
    }

    .flat-alternative-chart {
      height: 320px;
      width: 100%;
      min-width: 0;
      margin-top: 10px;
    }

    .analysis-list {
      margin: 10px 0 0 0;
      padding-left: 18px;
      color: rgba(78, 84, 93, 1);
      font-size: 13px;
      line-height: 20px;

      &.compact {
        margin-top: 8px;
      }
    }
  }
}

.sql-block {
  position: relative;

  .input-icon {
    min-width: unset;
    position: absolute;
    top: 12px;
    right: 12px;
    color: #1f2329;
    display: none;
    background-color: transparent !important;

    border-color: #dee0e3;
    box-shadow: 0px 4px 8px 0px #1f23291a;

    &:hover,
    &:focus {
      color: var(--ed-color-primary);
    }

    &:active {
      color: var(--ed-color-primary-dark-2);
    }
  }

  &:hover {
    .input-icon {
      display: flex;
    }
  }
}
</style>
