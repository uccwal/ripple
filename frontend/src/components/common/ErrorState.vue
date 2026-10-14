<script setup lang="ts">
import RpButton from './RpButton.vue'

/** 오류 + 다시 시도. 실행 실패 카드와 같은 시각 언어(테두리 #F3C3BD, ! 원 아이콘). */
withDefaults(defineProps<{ title?: string; message?: string | null; retryLabel?: string }>(), {
  title: '데이터를 불러오지 못했습니다',
  message: null,
  retryLabel: '다시 시도',
})
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="flex items-start gap-4 rounded-card border border-fail-line bg-surface p-6" role="alert">
    <span
      class="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-fail-bg text-base font-extrabold text-fail"
      aria-hidden="true"
      >!</span
    >
    <div class="flex min-w-0 flex-col gap-1">
      <div class="text-[15px] font-bold">{{ title }}</div>
      <div v-if="message" class="text-small text-ink-2">{{ message }}</div>
      <div class="mt-2 flex gap-2">
        <RpButton @click="$emit('retry')">{{ retryLabel }}</RpButton>
        <slot />
      </div>
    </div>
  </div>
</template>
