<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { chatApi, type ChatExecutionStep, type ChatLogHistoryItem } from '@/api/chat.ts'
import SQLComponent from '@/views/chat/component/SQLComponent.vue'
import icon_expand_right_filled from '@/assets/svg/icon_expand-right_filled.svg'
import gou_icon from '@/assets/svg/gou_icon.svg'
import icon_error from '@/assets/svg/icon_error.svg'
import { useChatConfigStore } from '@/stores/chatConfig.ts'

const props = withDefaults(
  defineProps<{
    recordId?: number
    steps?: Array<ChatExecutionStep>
    loading?: boolean
    finished?: boolean
  }>(),
  {
    recordId: undefined,
    steps: () => [],
    loading: false,
    finished: false,
  }
)

const { t } = useI18n()
const chatConfig = useChatConfigStore()
const historySteps = ref<Array<ChatExecutionStep>>([])
const loadedRecordId = ref<number | undefined>()
const expandIds = ref<Array<number>>([])

const visible = computed(() => chatConfig.getShowLog)

const displaySteps = computed(() => {
  return props.steps.length > 0 ? props.steps : historySteps.value
})

const hasSteps = computed(() => displaySteps.value.length > 0)

const title = computed(() => {
  if (props.loading && !props.finished) return t('chat.execution_process_running')
  return t('chat.execution_process')
})

function normalizeOperate(operate?: string) {
  if (!operate) return ''
  return t('chat.log.' + operate)
}

function statusClass(step: ChatExecutionStep) {
  if (step.status === 'error' || step.error) return 'error'
  if (step.status === 'skipped') return 'skipped'
  if (step.status === 'success') return 'success'
  return 'running'
}

function statusText(step: ChatExecutionStep) {
  if (step.status === 'error' || step.error) return t('chat.step_error')
  if (step.status === 'skipped') return t('chat.step_skipped')
  if (step.status === 'success') return t('chat.step_success')
  return t('chat.step_running')
}

function stepKey(step: ChatExecutionStep) {
  return step.operate_key || step.operate
}

function summarizeDetail(step: ChatExecutionStep) {
  const detail = step.detail
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (detail.datasource) return detail.datasource
  if (Array.isArray(detail.tables) && detail.tables.length > 0) {
    return detail.tables.join(', ')
  }
  if (typeof detail.count === 'number') return t('chat.query_count_title', [detail.count])
  if (detail.chart_type || detail.title) {
    return [detail.chart_type, detail.title].filter(Boolean).join(' / ')
  }
  if (detail.dimension) return detail.dimension
  return ''
}

function detailSql(step: ChatExecutionStep) {
  const detail = step.detail
  if (!detail || typeof detail !== 'object') return ''
  if (step.operate_key === 'EXECUTE_SQL' && typeof detail.sql === 'string') return detail.sql
  return typeof detail.sql === 'string' ? detail.sql : ''
}

function canExpand(step: ChatExecutionStep) {
  return !!detailSql(step) || !!step.message || !!summarizeDetail(step)
}

function toggle(index: number) {
  if (!canExpand(displaySteps.value[index])) return
  if (expandIds.value.includes(index)) {
    expandIds.value = expandIds.value.filter((item) => item !== index)
  } else {
    expandIds.value.push(index)
  }
}

function fromLogItem(item: ChatLogHistoryItem): ChatExecutionStep {
  return {
    operate: item.operate || normalizeOperate(item.operate_key),
    operate_key: item.operate_key,
    status: item.error ? 'error' : 'success',
    detail: item.message,
    duration: item.duration,
    total_tokens: item.total_tokens,
    error: item.error,
  }
}

function loadHistory() {
  if (!visible.value || !props.recordId || !props.finished || props.steps.length > 0) return
  if (loadedRecordId.value === props.recordId) return
  loadedRecordId.value = props.recordId
  chatApi.get_chart_log_history(props.recordId).then((res) => {
    const logHistory = chatApi.toChatLogHistory(res)
    historySteps.value = (logHistory?.steps || []).map(fromLogItem)
  })
}

watch(
  () => [props.recordId, props.finished, props.steps.length, visible.value],
  () => loadHistory()
)

onMounted(loadHistory)
</script>

<template>
  <div v-if="visible && (hasSteps || loading)" class="execution-process">
    <div class="process-title">{{ title }}</div>
    <div class="process-list">
      <div
        v-for="(step, index) in displaySteps"
        :key="`${stepKey(step)}-${index}`"
        class="process-item"
        :class="statusClass(step)"
      >
        <button class="process-header" type="button" @click="toggle(index)">
          <el-icon class="shrink" :class="expandIds.includes(index) && 'expand'" size="10">
            <icon_expand_right_filled />
          </el-icon>
          <span class="step-name">{{ step.operate || normalizeOperate(step.operate_key) }}</span>
          <span v-if="summarizeDetail(step)" class="step-summary">{{ summarizeDetail(step) }}</span>
          <span class="step-meta">
            <span v-if="step.total_tokens">{{ step.total_tokens }} tokens</span>
            <span v-if="step.duration !== undefined">{{ step.duration }}s</span>
            <span class="step-status">{{ statusText(step) }}</span>
            <el-icon v-if="step.status === 'success' && !step.error" size="14">
              <gou_icon />
            </el-icon>
            <el-icon v-else-if="step.status === 'error' || step.error" size="14">
              <icon_error />
            </el-icon>
          </span>
        </button>
        <div v-if="expandIds.includes(index)" class="process-detail">
          <div v-if="step.message" class="detail-text">{{ step.message }}</div>
          <SQLComponent v-if="detailSql(step)" :sql="detailSql(step)" />
          <div v-else-if="summarizeDetail(step)" class="detail-text">{{ summarizeDetail(step) }}</div>
        </div>
      </div>
      <div v-if="loading && !hasSteps" class="process-item running placeholder">
        {{ t('chat.step_running') }}
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.execution-process {
  margin: 8px 0 12px;
  border: 1px solid #dee0e3;
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
}

.process-title {
  padding: 10px 12px;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
  border-bottom: 1px solid #eff0f1;
  color: #1f2329;
}

.process-list {
  display: flex;
  flex-direction: column;
}

.process-item {
  border-bottom: 1px solid #eff0f1;

  &:last-child {
    border-bottom: none;
  }

  &.running .step-status {
    color: #3370ff;
  }

  &.success .step-status {
    color: #2f7d32;
  }

  &.error .step-status {
    color: #d93026;
  }

  &.skipped .step-status {
    color: #8f959e;
  }
}

.process-header {
  width: 100%;
  min-height: 38px;
  padding: 8px 12px;
  border: 0;
  background: transparent;
  display: grid;
  grid-template-columns: 14px max-content minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
  text-align: left;
  cursor: pointer;
  color: #1f2329;
}

.shrink {
  transition: transform 0.15s ease;
  color: #646a73;
}

.expand {
  transform: rotate(90deg);
}

.step-name {
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  white-space: nowrap;
}

.step-summary {
  min-width: 0;
  color: #646a73;
  font-size: 12px;
  line-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: #646a73;
  white-space: nowrap;
}

.process-detail {
  margin: 0 12px 12px 32px;
  padding: 10px;
  border-radius: 6px;
  background: #f5f6f7;
  color: #646a73;
  font-size: 12px;
  line-height: 20px;

  :deep(.hljs) {
    margin: 0;
    padding: 10px;
    border-radius: 6px;
  }
}

.detail-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.placeholder {
  padding: 10px 12px;
  color: #646a73;
  font-size: 13px;
}
</style>
