<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'
import { useUiStore } from '@/stores/ui'
import { formatEok, formatPct, formatPp, formatWithUnit, pnlColor } from '@/utils/format'

/**
 * 클릭 가능한 수치 (README 전역 규칙)
 * - 점선 밑줄: underline dotted, 두께 1px, offset 3px(본문) / 4px(16px) / 5px(30px)
 * - 손익색: 이익 #D23F31, 손실 #1E5BD8, 0 #4A5363, 없음 #7A8394 · 부호 U+2212 · tabular-nums
 * - runId + calcKey → S5 계산 근거 패널, to → 화면 이동
 * - interactive=false: 같은 모양이지만 클릭은 부모 행이 처리 (중첩 버튼 방지)
 */
const props = withDefaults(
  defineProps<{
    value?: number | null
    /** 직접 지정한 표기 (범위 등). 없으면 value + unit으로 만든다. */
    text?: string
    unit?: string
    digits?: number
    runId?: string | null
    calcKey?: string
    to?: RouteLocationRaw
    /** pnl: 손익색 · neutral: 본문색 · inherit: 부모 색 */
    tone?: 'pnl' | 'neutral' | 'inherit'
    offset?: 3 | 4 | 5
    interactive?: boolean
    label?: string
  }>(),
  {
    value: null,
    text: undefined,
    unit: '%',
    digits: undefined,
    runId: null,
    calcKey: undefined,
    to: undefined,
    tone: 'pnl',
    offset: 3,
    interactive: true,
    label: undefined,
  },
)

const ui = useUiStore()
const router = useRouter()

const resolvedDigits = computed(() => props.digits ?? (props.unit === '%p' ? 2 : props.unit === '억 원' ? 0 : 1))

const display = computed(() => {
  if (props.text !== undefined) return props.text
  if (props.unit === '%') return formatPct(props.value, resolvedDigits.value)
  if (props.unit === '%p') return formatPp(props.value, resolvedDigits.value)
  if (props.unit === '억 원') return formatEok(props.value)
  return formatWithUnit(props.value, props.unit, { digits: resolvedDigits.value })
})

const color = computed(() => {
  if (props.tone === 'inherit') return undefined
  if (props.tone === 'neutral') return '#141A24'
  return pnlColor(props.value, resolvedDigits.value)
})

const canClick = computed(() => props.interactive && (!!props.to || (!!props.runId && !!props.calcKey)))

const style = computed(() => ({
  color: color.value,
  textUnderlineOffset: `${props.offset}px`,
}))

function onClick(ev: MouseEvent): void {
  ev.stopPropagation()
  if (props.to) {
    void router.push(props.to)
  } else if (props.runId && props.calcKey) {
    ui.openCalc(props.runId, props.calcKey)
  }
}
</script>

<template>
  <button
    v-if="canClick"
    type="button"
    class="calc-num calc-num--btn"
    :style="style"
    :aria-label="label ? `${label} ${display} — 계산 근거 보기` : undefined"
    @click="onClick"
  >
    {{ display }}
  </button>
  <span v-else class="calc-num" :style="style">{{ display }}</span>
</template>

<style scoped>
/*
 * 버튼 기본값(배경·테두리·패딩·글꼴 상속·cursor)은 Tailwind preflight가 이미 초기화한다.
 * 여기서 font 등을 다시 지정하면 부모가 넘긴 text-display 같은 유틸리티를 덮어쓰므로 두지 않는다.
 */
.calc-num {
  font-variant-numeric: tabular-nums;
  text-decoration-line: underline;
  text-decoration-style: dotted;
  text-decoration-thickness: 1px;
  white-space: nowrap;
}
</style>
