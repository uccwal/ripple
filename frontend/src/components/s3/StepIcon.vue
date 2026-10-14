<script setup lang="ts">
import { computed } from 'vue'
import type { StepStatus } from '@/api/types'
import RpSpinner from '@/components/common/RpSpinner.vue'
import { STEP_VISUAL } from '@/utils/labels'

/** 타임라인 상태 아이콘: 24px 원, 테두리 1.5px (README S3 표) */
const props = defineProps<{ status: StepStatus }>()
const v = computed(() => STEP_VISUAL[props.status])
</script>

<template>
  <div
    class="relative z-[1] flex h-6 w-6 flex-none items-center justify-center rounded-full text-caption font-bold"
    :style="{ background: v.bg, border: `1.5px solid ${v.border}`, color: v.glyphColor }"
    aria-hidden="true"
  >
    <RpSpinner v-if="status === 'running'" />
    <template v-else>{{ v.glyph }}</template>
  </div>
</template>
