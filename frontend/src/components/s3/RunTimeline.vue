<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { RetryLoop, Step } from '@/api/types'
import { formatElapsed } from '@/utils/format'
import TimelineStep from './TimelineStep.vue'

/**
 * S3 좌측 "실행 과정" 패널 내용.
 * 반려 루프 화살표: retry_loops 의 to_idx(재실행 대상) 아이콘 중심 ~ from_idx(Validator) 아이콘 중심.
 * 위치는 DOM 측정 — 단계를 펼치거나 메모가 늘어나면 ResizeObserver로 다시 잰다.
 */
const props = defineProps<{
  runId: string
  steps: Step[]
  retryLoops: RetryLoop[]
  elapsedMs: number | null
  active: boolean
  expanded: number | null
  modelNote: string
  modelTip?: string
}>()
defineEmits<{ toggle: [idx: number] }>()

const listEl = ref<HTMLElement | null>(null)
const brackets = ref<{ key: string; top: number; height: number }[]>([])

/** 아이콘 중심 = 항목 상단 패딩 10 + 아이콘 반지름 12 */
const ICON_CENTER = 22

function measure(): void {
  const el = listEl.value
  if (!el) return
  const next: { key: string; top: number; height: number }[] = []
  for (const loop of props.retryLoops) {
    const lo = Math.min(loop.to_idx, loop.from_idx)
    const hi = Math.max(loop.to_idx, loop.from_idx)
    const a = el.querySelector<HTMLElement>(`[data-step="${lo}"]`)
    const b = el.querySelector<HTMLElement>(`[data-step="${hi}"]`)
    if (!a || !b) continue
    const key = `${loop.from_idx}-${loop.to_idx}`
    if (next.some((n) => n.key === key)) continue
    next.push({ key, top: a.offsetTop + ICON_CENTER, height: b.offsetTop - a.offsetTop })
  }
  brackets.value = next
}

let ro: ResizeObserver | null = null
onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined' && listEl.value) {
    ro = new ResizeObserver(() => measure())
    ro.observe(listEl.value)
  }
})
onBeforeUnmount(() => ro?.disconnect())
watch(
  () => [props.steps, props.retryLoops, props.expanded],
  () => nextTick(measure),
  { deep: true },
)

const elapsedText = computed(() => {
  if (props.elapsedMs === null) return ''
  return props.active ? formatElapsed(props.elapsedMs) : `총 ${formatElapsed(props.elapsedMs)}`
})
</script>

<template>
  <div class="flex h-full flex-col gap-3 px-4 py-[18px]">
    <div class="flex items-baseline justify-between">
      <h2 class="m-0 text-body font-bold">실행 과정</h2>
      <span class="tnum text-caption font-normal text-ink-3" aria-live="off">{{ elapsedText }}</span>
    </div>
    <div class="font-mono text-[11px] font-medium text-ink-3">{{ runId }}</div>

    <div ref="listEl" class="relative">
      <div class="absolute bottom-[22px] left-[11px] top-[22px] w-0.5 bg-line" aria-hidden="true" />
      <ol class="m-0 flex list-none flex-col p-0">
        <TimelineStep v-for="s in steps" :key="s.idx" :step="s" :expanded="expanded === s.idx" @toggle="$emit('toggle', s.idx)" />
      </ol>
      <div
        v-for="b in brackets"
        :key="b.key"
        class="pointer-events-none absolute right-2 w-[18px] rounded-r-card border-[1.5px] border-l-0 border-warn-loop"
        :style="{ top: `${b.top}px`, height: `${b.height}px` }"
        aria-hidden="true"
      >
        <span class="absolute -left-[7px] -top-[9px] text-[11px] leading-none text-warn-loop">◀</span>
        <span
          class="absolute -right-[9px] top-1/2 -translate-y-1/2 bg-white py-1 text-[11px] font-bold text-warn [writing-mode:vertical-rl]"
          >반려</span
        >
      </div>
    </div>

    <div class="mt-auto flex flex-col gap-0.5 border-t border-line-subtle pt-3 text-caption font-normal text-ink-3">
      <span>단계를 누르면 입력·출력 요약을 펼칩니다.</span>
      <span :title="modelTip" :class="{ 'cursor-help': modelTip }">{{ modelNote }}</span>
    </div>
  </div>
</template>
