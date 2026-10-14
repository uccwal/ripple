<script setup lang="ts">
import { computed } from 'vue'
import type { Step } from '@/api/types'
import { formatElapsed } from '@/utils/format'
import { STEP_VISUAL } from '@/utils/labels'
import StepIcon from './StepIcon.vue'

const props = defineProps<{ step: Step; expanded: boolean }>()
defineEmits<{ toggle: [] }>()

const v = computed(() => STEP_VISUAL[props.step.status])

const time = computed(() => {
  const s = props.step
  if (s.status === 'running') return '…'
  if (s.status === 'wait' || s.status === 'skip') return ''
  return formatElapsed(s.elapsed_ms)
})

/** 메모 박스 색: 실패 / 반려·경고 / 통과 */
const noteTone = computed(() => {
  const s = props.step
  if (s.status === 'failed') return 'bg-fail-bg text-fail'
  if (s.status === 'retry' || (s.note ?? '').includes('반려') || (s.note ?? '').includes('경고')) return 'bg-warn-note text-warn'
  return 'bg-pass-bg text-pass'
})

const detailId = computed(() => `step-detail-${props.step.idx}`)
</script>

<template>
  <li :data-step="step.idx" class="relative flex gap-3 py-2.5 pl-0 pr-10">
    <StepIcon :status="step.status" />
    <div class="min-w-0 flex-1">
      <button
        type="button"
        class="flex w-full cursor-pointer items-baseline gap-1.5 border-0 bg-transparent p-0 text-left"
        :aria-expanded="expanded"
        :aria-controls="detailId"
        @click="$emit('toggle')"
      >
        <span class="ellipsis min-w-0 text-small font-bold" :style="{ color: v.nameColor }">{{ step.idx + 1 }}. {{ step.agent }}</span>
        <span class="tnum ml-auto whitespace-nowrap text-caption font-normal text-ink-3">{{ time }}</span>
      </button>
      <div class="flex items-center gap-1.5 text-caption font-normal text-ink-3">
        <span>{{ step.desc }}</span><span aria-hidden="true">·</span>
        <span class="whitespace-nowrap font-semibold" :style="{ color: v.labelColor }">{{ v.label }}</span>
        <span
          v-if="step.attempt >= 2"
          class="flex h-[18px] flex-none items-center whitespace-nowrap rounded-xs bg-warn-bg px-1.5 text-[11px] font-semibold text-warn"
          >{{ step.attempt }}회 시도</span
        >
      </div>
      <div v-if="step.note" class="mt-1.5 rounded-sm px-2 py-1.5 text-caption font-normal leading-[1.45]" :class="noteTone">
        {{ step.note }}
      </div>
      <div
        v-if="expanded"
        :id="detailId"
        class="mt-2 grid grid-cols-[44px_minmax(0,1fr)] gap-x-2 gap-y-1 rounded bg-bg p-2.5 text-caption font-normal"
      >
        <span class="text-ink-3">입력</span><span class="break-words">{{ step.input_summary || '—' }}</span>
        <span class="text-ink-3">출력</span><span class="break-words">{{ step.output_summary || '—' }}</span>
        <span class="text-ink-3">모델</span><span class="break-words font-mono text-[11px]">{{ step.model || '—' }}</span>
        <span class="text-ink-3">토큰</span><span class="tnum">{{ step.tokens || '—' }}</span>
      </div>
    </div>
  </li>
</template>
