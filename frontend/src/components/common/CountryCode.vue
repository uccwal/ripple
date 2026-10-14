<script setup lang="ts">
/** 국가 코드 박스 30×20, navy, 11px/700 mono */
withDefaults(defineProps<{ code: string; tone?: 'navy' | 'white' }>(), { tone: 'navy' })
</script>

<template>
  <span
    class="flex h-5 w-[30px] flex-none items-center justify-center rounded-xs font-mono text-[11px] font-bold text-navy-900"
    :class="tone === 'navy' ? 'bg-navy-50' : 'bg-white'"
  >
    {{ code }}
  </span>
</template>
