<script setup lang="ts">
import RpButton from '@/components/common/RpButton.vue'

defineProps<{ reason: string | null; retryPending: boolean }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="flex items-start gap-5 rounded-card border border-fail-line bg-surface p-8" role="alert">
    <span class="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-fail-bg text-lg font-extrabold text-fail" aria-hidden="true">!</span>
    <div class="flex flex-col gap-1.5">
      <div class="text-heading font-bold">분석을 완료하지 못했습니다</div>
      <div class="max-w-[640px] text-small text-ink-2">
        {{ reason || '실행 중 오류가 발생했습니다. 단계별 메모에서 실패 지점을 확인할 수 있습니다.' }}
      </div>
      <div class="mt-2.5 flex gap-2">
        <RpButton :disabled="retryPending" @click="$emit('retry')">다시 시도</RpButton>
        <RpButton variant="secondary" :to="{ name: 'runs' }">실행 이력으로</RpButton>
      </div>
    </div>
  </div>
</template>
