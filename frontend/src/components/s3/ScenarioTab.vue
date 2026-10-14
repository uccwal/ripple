<script setup lang="ts">
import { computed } from 'vue'
import type { RunState } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import RpButton from '@/components/common/RpButton.vue'
import type { DraftRow } from '@/stores/run'
import { useUiStore } from '@/stores/ui'
import { pnlColor, shockDigits } from '@/utils/format'

/**
 * 탭② 시나리오 — 충격값 표. 값을 고치면(dirty) 행 배경 #FFFCF2·입력 테두리 #D9A92E,
 * 숫자가 아니면 테두리 #B42318 + "숫자 형식을 확인하세요". 재계산 → PATCH → 새 실행.
 */
const props = defineProps<{
  run: RunState
  rows: DraftRow[]
  dirty: boolean
  invalid: boolean
  canRecalc: boolean
  pending: boolean
  error: string | null
}>()
const emit = defineEmits<{ edit: [variable: string, text: string]; reset: []; recalc: [] }>()

const ui = useUiStore()
const GRID = 'grid-cols-[150px_120px_60px_minmax(0,1fr)_260px]'

const view = computed(() =>
  props.rows.map((r) => {
    const { shock } = r
    const v = r.parsed ?? shock.change
    // 수정하지 않은 행은 서버 값(hist_pct)을, 수정 중이면 입력값으로 다시 계산한다.
    const pct = !r.changed ? shock.hist_pct : shock.hist_max > 0 ? (Math.abs(v) / shock.hist_max) * 100 : shock.hist_pct
    const over = pct > 100
    return {
      ...r,
      color: pnlColor(v, shockDigits(shock.unit)),
      border: r.invalid ? '#B42318' : r.changed ? '#D9A92E' : '#CDD2DA',
      barW: `${Math.min(pct, 100)}%`,
      over,
      posText: over ? `최대 초과 ${Math.round(pct)}%` : `${Math.round(pct)}%`,
    }
  }),
)

function open(variable: string): void {
  ui.openCalc(props.run.run_id, `f:${variable}`)
}

function onEnter(): void {
  if (props.canRecalc) emit('recalc')
}
</script>

<template>
  <EmptyState
    v-if="rows.length === 0"
    title="시나리오 충격값이 없습니다"
    description="Scenario Builder 단계가 충격값을 만들지 못했습니다. 실행 과정의 단계 메모를 확인하세요."
  />
  <div v-else class="rp-card overflow-hidden">
    <div class="rp-thead grid gap-4 border-b border-line px-5 py-2.5" :class="GRID" role="row">
      <span>변수</span><span class="text-right">충격값</span><span>단위</span><span>근거</span><span>과거 최대 변동폭 대비 위치</span>
    </div>

    <div
      v-for="r in view"
      :key="r.shock.variable"
      class="grid items-center gap-4 border-b border-line-subtle px-5 py-2.5"
      :class="[GRID, r.changed ? 'bg-warn-row' : 'bg-white']"
      role="row"
    >
      <div class="min-w-0">
        <button type="button" class="block cursor-pointer border-0 bg-transparent p-0 text-left text-body font-semibold text-ink" @click="open(r.shock.variable)">
          {{ r.shock.name }}
        </button>
        <div class="font-mono text-[11px] text-ink-3">{{ r.shock.variable }}</div>
      </div>
      <input
        :value="r.text"
        class="tnum h-[34px] w-full rounded border bg-white px-2.5 text-right text-body font-bold outline-none focus:shadow-focus"
        :style="{ borderColor: r.border, color: r.invalid ? '#141A24' : r.color }"
        :aria-label="`${r.shock.name} 충격값 (${r.shock.unit})`"
        :aria-invalid="r.invalid"
        inputmode="decimal"
        autocomplete="off"
        @input="emit('edit', r.shock.variable, ($event.target as HTMLInputElement).value)"
        @keydown.enter="onEnter"
      />
      <span class="text-small text-ink-2">{{ r.shock.unit }}</span>
      <button
        type="button"
        class="cursor-pointer border-0 bg-transparent p-0 text-left text-small text-ink-2 underline decoration-line-strong decoration-dotted underline-offset-[3px]"
        @click="open(r.shock.variable)"
      >
        {{ r.shock.basis }}
      </button>
      <div class="flex items-center gap-2.5">
        <div class="relative h-2 flex-1 rounded-sm bg-line-subtle">
          <div class="absolute bottom-0 left-0 top-0 rounded-sm" :class="r.over ? 'bg-warn-loop' : 'bg-navy-300'" :style="{ width: r.barW }" />
          <div class="absolute -top-[3px] right-0 h-3.5 w-0.5 bg-ink-3" aria-hidden="true" />
        </div>
        <span class="tnum w-[86px] text-right text-caption font-normal" :class="r.over ? 'text-warn' : 'text-ink-2'">{{ r.posText }}</span>
      </div>
    </div>

    <div class="flex items-center gap-2.5 px-5 py-3.5">
      <span class="text-caption font-normal text-ink-3">
        충격값을 고치면 새 실행이 만들어지고 Regime Finder부터 다시 계산합니다. 막대 끝 눈금 = 과거 {{ run.scenario?.horizon_days ?? run.horizon_days }}영업일 최대 변동폭.
      </span>
      <span v-if="invalid" class="whitespace-nowrap text-caption font-semibold text-fail" role="alert">숫자 형식을 확인하세요</span>
      <span v-else-if="error" class="whitespace-nowrap text-caption font-semibold text-fail" role="alert">{{ error }}</span>
      <RpButton class="ml-auto" variant="secondary" :disabled="(!dirty && !invalid) || pending" @click="emit('reset')">되돌리기</RpButton>
      <RpButton :disabled="!canRecalc" @click="emit('recalc')">{{ pending ? '재계산 중…' : '재계산' }}</RpButton>
    </div>
  </div>
</template>
