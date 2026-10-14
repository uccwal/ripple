<script setup lang="ts">
import { computed } from 'vue'

/** README "배지" 표 — 높이 22, 패딩 0 8, radius 4, 12px/600, 줄바꿈 금지 */
export type BadgeVariant =
  | 'pass'
  | 'warn'
  | 'fail'
  | 'virtual'
  | 'conf-high'
  | 'conf-mid'
  | 'conf-low'
  | 'entry'
  | 'outline'

const props = withDefaults(defineProps<{ variant: BadgeVariant; tooltip?: string; tall?: boolean }>(), {
  tall: false,
})

const VARIANT: Record<BadgeVariant, string> = {
  pass: 'bg-pass-bg text-pass',
  warn: 'bg-warn-bg text-warn',
  fail: 'bg-fail-bg text-fail',
  virtual: 'bg-navy-50 text-navy-900 border border-dashed border-navy-300',
  'conf-high': 'bg-navy-900 text-white',
  'conf-mid': 'bg-navy-100 text-navy-700',
  'conf-low': 'bg-white text-ink-3 border border-dashed border-ink-4',
  entry: 'bg-navy-50 text-navy-900',
  outline: 'bg-white text-ink-2 border border-line-strong',
}

const cls = computed(() => [
  'inline-flex items-center gap-1 whitespace-nowrap flex-none rounded-sm text-caption',
  props.tall ? 'h-6 px-2.5 font-bold' : 'h-[22px] px-2 font-semibold',
  VARIANT[props.variant],
  props.tooltip ? 'cursor-help' : '',
])
</script>

<template>
  <span :class="cls" :title="tooltip"><slot /></span>
</template>
