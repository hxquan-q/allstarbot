<script setup lang="ts">
import md from '@/utils/markdown.ts'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { refThrottled } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  message?: string
}>()

const { t } = useI18n()

const rootRef = ref<HTMLElement>()

// During streaming, props.message changes on every token. Re-parsing the whole
// document each time causes visible flicker / garbled partial blocks. Throttle
// the source so we re-render at most once per frame window (~90ms); leading +
// trailing edges guarantee the first chunk renders immediately and the final
// state always flushes.
const source = computed(() => props.message ?? '')
const throttled = refThrottled(source, 90, true, true)

const renderMd = computed(() => md.render(throttled.value))

// Inject a copy button into each code block after the DOM updates. Done in JS
// (not inline onclick) so it survives the v-dompurify-html sanitization.
function enhanceCodeBlocks() {
  const root = rootRef.value
  if (!root) return
  root.querySelectorAll('pre').forEach((pre) => {
    if (pre.parentElement?.classList.contains('md-code-block')) return
    const wrap = document.createElement('div')
    wrap.className = 'md-code-block'
    pre.parentNode?.insertBefore(wrap, pre)
    wrap.appendChild(pre)

    const btn = document.createElement('button')
    btn.type = 'button'
    btn.className = 'md-copy-btn'
    btn.textContent = t('datasource.copy')
    btn.addEventListener('click', () => {
      const text = pre.textContent ?? ''
      copyText(text)
        .then(() => {
          btn.textContent = t('qa.copied')
          btn.classList.add('copied')
          window.setTimeout(() => {
            btn.textContent = t('datasource.copy')
            btn.classList.remove('copied')
          }, 1500)
        })
        .catch(() => undefined)
    })
    wrap.appendChild(btn)
  })
}

function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text)
  }
  // Fallback for non-secure contexts.
  return new Promise((resolve, reject) => {
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      resolve()
    } catch (e) {
      reject(e)
    }
  })
}

watch(renderMd, () => {
  nextTick(enhanceCodeBlocks)
})

onMounted(() => {
  nextTick(enhanceCodeBlocks)
})
</script>

<template>
  <div ref="rootRef" v-dompurify-html="renderMd" class="markdown-body md-render-container"></div>
</template>

<style lang="less"></style>
