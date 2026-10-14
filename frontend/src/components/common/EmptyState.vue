<script setup lang="ts">
/** 데이터 없음: 점선 카드 (1px dashed #CDD2DA, 패딩 48, 가운데 정렬) */
withDefaults(defineProps<{ title: string; description?: string; compact?: boolean }>(), { compact: false })
</script>

<template>
  <div
    class="flex flex-col items-center gap-3 rounded-card border border-dashed border-line-strong bg-surface text-center"
    :class="compact ? 'p-8' : 'p-12'"
  >
    <div class="text-[15px] font-semibold">{{ title }}</div>
    <div v-if="description" class="text-small text-ink-3">{{ description }}</div>
    <div v-if="$slots.default" class="mt-1.5 flex gap-2"><slot /></div>
  </div>
</template>
