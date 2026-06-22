<script setup lang="ts">
import logoUrl from '@/assets/weallstar.png'

const props = withDefaults(
  defineProps<{
    width?: number | string
    height?: number | string
    alt?: string
  }>(),
  {
    width: 30,
    height: 30,
    alt: '小爱同学',
  }
)

const sizeValue = (value: number | string) => {
  return typeof value === 'number' ? `${value}px` : value
}
</script>

<template>
  <img
    class="brand-logo"
    :src="logoUrl"
    :alt="props.alt"
    :style="{ width: sizeValue(props.width), height: sizeValue(props.height) }"
  />
</template>

<style scoped>
.brand-logo {
  display: inline-block;
  flex-shrink: 0;
  object-fit: contain;
  vertical-align: middle;
}
</style>
