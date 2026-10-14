<script setup lang="ts">
/** 필터 칩: 높이 28, 패딩 0 12, radius 14, 13px/600 */
defineProps<{ selected: boolean }>()
defineEmits<{ click: [] }>()
</script>

<template>
  <button
    type="button"
    class="flex h-7 flex-none cursor-pointer items-center whitespace-nowrap rounded-[14px] border px-3 text-small font-semibold"
    :class="selected ? 'border-navy-900 bg-navy-900 text-white' : 'border-line-strong bg-white text-ink-2'"
    :aria-pressed="selected"
    @click="$emit('click')"
  >
    <slot />
  </button>
</template>
