<script setup lang="ts">
import BaseAnswer from './BaseAnswer.vue'
import {
  Chat,
  chatApi,
  ChatInfo,
  type ChatExecutionStep,
  type ChatMessage,
  ChatRecord,
  questionApi,
} from '@/api/chat.ts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ChartBlock from '@/views/chat/chat-block/ChartBlock.vue'
import JSONBig from 'json-bigint'
import ExecutionProcess from '@/views/chat/ExecutionProcess.vue'
import { i18n } from '@/i18n'
import { extractSSEFrames } from '@/utils/sse'

const { t } = i18n.global

const props = withDefaults(
  defineProps<{
    recordId?: number
    chatList?: Array<ChatInfo>
    currentChatId?: number
    currentChat?: ChatInfo
    message?: ChatMessage
    loading?: boolean
    reasoningName: 'sql_answer' | 'chart_answer' | Array<'sql_answer' | 'chart_answer'>
  }>(),
  {
    recordId: undefined,
    chatList: () => [],
    currentChatId: undefined,
    currentChat: () => new ChatInfo(),
    message: undefined,
    loading: false,
  }
)

const emits = defineEmits([
  'finish',
  'error',
  'stop',
  'scrollBottom',
  'update:loading',
  'update:chatList',
  'update:currentChat',
  'update:currentChatId',
])

const index = computed(() => {
  if (props.message?.index) {
    return props.message.index
  }
  if (props.message?.index === 0) {
    return 0
  }
  return -1
})

const _currentChatId = computed({
  get() {
    return props.currentChatId
  },
  set(v) {
    emits('update:currentChatId', v)
  },
})

const _currentChat = computed({
  get() {
    return props.currentChat
  },
  set(v) {
    emits('update:currentChat', v)
  },
})

const _chatList = computed({
  get() {
    return props.chatList
  },
  set(v) {
    emits('update:chatList', v)
  },
})

const _loading = computed({
  get() {
    return props.loading
  },
  set(v) {
    emits('update:loading', v)
  },
})

const stopFlag = ref(false)

function toOperateName(operate?: string) {
  if (!operate) return ''
  return t('chat.log.' + operate)
}

function upsertExecutionStep(payload: any) {
  if (index.value < 0) return
  const record = _currentChat.value.records[index.value]
  if (!record.execution_steps) {
    record.execution_steps = []
  }
  const step: ChatExecutionStep = {
    operate: toOperateName(payload.operate),
    operate_key: payload.operate,
    status: payload.status || 'running',
    message: payload.message,
    detail: payload.detail,
  }
  let existIndex = -1
  for (let i = record.execution_steps.length - 1; i >= 0; i--) {
    const item = record.execution_steps[i]
    if (
      item.operate_key === step.operate_key &&
      (item.status === 'running' || step.status !== 'running' || !!step.detail)
    ) {
      existIndex = i
      break
    }
  }
  if (existIndex >= 0) {
    record.execution_steps[existIndex] = {
      ...record.execution_steps[existIndex],
      ...step,
    }
  } else {
    record.execution_steps.push(step)
  }
}

const sendMessage = async () => {
  stopFlag.value = false
  _loading.value = true

  if (index.value < 0) {
    _loading.value = false
    return
  }

  const currentRecord: ChatRecord = _currentChat.value.records[index.value]

  let error: boolean = false
  if (_currentChatId.value === undefined) {
    error = true
  }
  if (error) return

  try {
    const controller: AbortController = new AbortController()
    const param = {
      question: currentRecord.question,
      chat_id: _currentChatId.value,
    }
    const response = await questionApi.add(param, controller)
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')

    let sql_answer = ''
    let chart_answer = ''
    currentRecord.execution_steps = []

    let tempResult = ''

    while (true) {
      if (stopFlag.value) {
        controller.abort()
        break
      }

      const { done, value } = await reader.read()
      if (done) {
        _loading.value = false
        break
      }

      let chunk = decoder.decode(value, { stream: true })
      tempResult += chunk
      const parsed = extractSSEFrames(tempResult)
      tempResult = parsed.remainder
      const split = parsed.frames.length ? parsed.frames.map((f) => 'data:' + f + '\n\n') : null
      if (split) {
        chunk = split.join('')
      } else {
        continue
      }
      if (chunk && chunk.startsWith('data:{')) {
        if (split) {
          for (const str of split) {
            let data
            try {
              data = JSONBig.parse(str.replace('data:{', '{'))
            } catch (err) {
              console.error('JSON string:', str)
              throw err
            }

            if (data.code && data.code !== 200) {
              ElMessage({
                message: data.msg,
                type: 'error',
                showClose: true,
              })
              _loading.value = false
              return
            }

            switch (data.type) {
              case 'id':
                currentRecord.id = data.id
                _currentChat.value.records[index.value].id = data.id
                break
              case 'regenerate_record_id':
                currentRecord.regenerate_record_id = data.regenerate_record_id
                _currentChat.value.records[index.value].regenerate_record_id =
                  data.regenerate_record_id
                break
              case 'question':
                currentRecord.question = data.question
                _currentChat.value.records[index.value].question = data.question
                break
              case 'info':
                console.info(data.msg)
                break
              case 'progress':
                upsertExecutionStep(data)
                break
              case 'brief':
                _currentChat.value.brief = data.brief
                _chatList.value.forEach((c: Chat) => {
                  if (c.id === _currentChat.value.id) {
                    c.brief = _currentChat.value.brief
                  }
                })
                break
              case 'error':
                currentRecord.error = data.content
                currentRecord.execution_steps?.forEach((step) => {
                  if (step.status === 'running') {
                    step.status = 'error'
                    step.error = true
                  }
                })
                emits('error', currentRecord.id)
                break
              case 'sql-result':
                sql_answer += data.reasoning_content
                _currentChat.value.records[index.value].sql_answer = sql_answer
                break
              case 'sql':
                _currentChat.value.records[index.value].sql = data.content
                break
              case 'sql-data':
                getChatData(_currentChat.value.records[index.value].id)
                break
              case 'chart-result':
                chart_answer += data.reasoning_content
                _currentChat.value.records[index.value].chart_answer = chart_answer
                break
              case 'chart':
                _currentChat.value.records[index.value].chart = data.content
                break
              case 'dimension-start':
                _currentChat.value.records[index.value].dimensions = []
                break
              case 'dimension-result':
                if (!_currentChat.value.records[index.value].dimensions) {
                  _currentChat.value.records[index.value].dimensions = []
                }
                _currentChat.value.records[index.value].dimensions?.push(data.content)
                break
              case 'dimension-finish':
                getChatData(_currentChat.value.records[index.value].id)
                break
              case 'datasource':
                if (!_currentChat.value.datasource) {
                  _currentChat.value.datasource = data.id
                }
                break
              case 'finish':
                _currentChat.value.records[index.value].finish = true
                emits('finish', currentRecord.id)
                break
            }
            await nextTick()
          }
        }
      }
    }
  } catch (error) {
    if (!currentRecord.error) {
      currentRecord.error = ''
    }
    if (currentRecord.error.trim().length !== 0) {
      currentRecord.error = currentRecord.error + '\n'
    }
    currentRecord.error = currentRecord.error + 'Error:' + error
    console.error('Error:', error)
    emits('error')
  } finally {
    _loading.value = false
  }
}

const loadingData = ref(false)

function getChatData(recordId?: number) {
  loadingData.value = true
  chatApi
    .get_chart_data(recordId)
    .then((response) => {
      _currentChat.value.records.forEach((record) => {
        if (record.id === recordId) {
          record.data = response
        }
      })
    })
    .finally(() => {
      loadingData.value = false
      emits('scrollBottom')
    })
}

function stop() {
  stopFlag.value = true
  _loading.value = false
  emits('stop')
}

onBeforeUnmount(() => {
  stop()
})

onMounted(() => {
  if (props.message?.record?.id && props.message?.record?.finish) {
    getChatData(props.message.record.id)
  }
})

defineExpose({ sendMessage, index: () => index.value, stop })
</script>

<template>
  <BaseAnswer v-if="message" :message="message" :reasoning-name="reasoningName" :loading="_loading">
    <ExecutionProcess
      :record-id="message.record?.id"
      :steps="message.record?.execution_steps"
      :loading="_loading || !!message.isTyping"
      :finished="!!message.record?.finish"
    />
    <ChartBlock
      style="margin-top: 6px"
      :message="message"
      :record-id="recordId"
      :loading-data="loadingData"
    />
    <slot></slot>
    <template #tool>
      <slot name="tool"></slot>
    </template>
    <template #footer>
      <slot name="footer"></slot>
    </template>
  </BaseAnswer>
</template>

<style scoped lang="less"></style>
