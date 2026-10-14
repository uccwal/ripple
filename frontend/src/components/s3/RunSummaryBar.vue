<script setup lang="ts">
import { computed } from 'vue'
import type { RunState } from '@/api/types'
import CalcNum from '@/components/common/CalcNum.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import RpButton from '@/components/common/RpButton.vue'
import { formatRange, pnlColor } from '@/utils/format'

const props = defineProps<{ run: RunState; rerunPending: boolean }>()
defineEmits<{ download: []; rerun: [] }>()

const result = computed(() => props.run.result)
const validation = computed(() => props.run.validation)

/** 근거 불충분(low_evidence) 경고는 따로 묶고, 그 외 경고는 "경고 N"으로 */
const lowEvidence = computed(() => validation.value?.issues.filter((i) => i.code === 'low_evidence') ?? [])
const otherWarnings = computed(
  () => validation.value?.issues.filter((i) => i.code !== 'low_evidence' && i.severity === 'warn') ?? [],
)
const errors = computed(() => validation.value?.issues.filter((i) => i.severity === 'error') ?? [])
const overHist = computed(() => props.run.scenario?.shocks.filter((s) => s.over_hist) ?? [])

const tip = (items: { agent?: string; message: string }[]) =>
  items.map((i) => (i.agent ? `[${i.agent}] ${i.message}` : i.message)).join('\n')
const overHistTip = computed(() =>
  overHist.value.map((s) => `${s.name}: 과거 최대 변동폭 대비 ${Math.round(s.hist_pct)}%`).join('\n'),
)
const amountColor = computed(() => pnlColor(result.value?.portfolio_pnl, 1))
</script>

<template>
  <div class="rp-card flex items-center gap-7 px-5 py-3.5">
    <div>
      <div class="text-caption font-normal text-ink-3">포트폴리오 예상 손익</div>
      <div class="flex items-baseline gap-2">
        <CalcNum
          class="text-display font-bold tracking-[-0.02em]"
          :value="result?.portfolio_pnl"
          :run-id="run.run_id"
          calc-key="pnl"
          :offset="5"
          label="포트폴리오 예상 손익"
        />
        <span class="whitespace-nowrap text-body font-semibold" :style="{ color: amountColor }">
          (<CalcNum :value="result?.pnl_amount" unit="억 원" :run-id="run.run_id" calc-key="amt" tone="inherit" label="예상 손익 금액" />)
        </span>
      </div>
    </div>
    <div class="w-px self-stretch bg-line-subtle" aria-hidden="true" />
    <div>
      <div class="text-caption font-normal text-ink-3">추정 범위 (95%)</div>
      <CalcNum
        class="text-heading font-semibold"
        :text="formatRange(result?.range.low, result?.range.high)"
        :run-id="run.run_id"
        calc-key="range"
        tone="neutral"
        :offset="4"
        label="추정 범위"
      />
    </div>
    <div class="w-px self-stretch bg-line-subtle" aria-hidden="true" />
    <div>
      <div class="mb-1 text-caption font-normal text-ink-3">검증 상태</div>
      <div class="flex gap-1.5">
        <template v-if="validation">
          <RpBadge v-if="validation.status === 'fail'" variant="fail" :tooltip="tip(errors) || undefined">! 검증 실패</RpBadge>
          <RpBadge v-else variant="pass" :tooltip="`검증 규칙 ${validation.rules_passed}/${validation.rules_total} 통과`">✓ 검증 통과</RpBadge>
          <RpBadge v-if="lowEvidence.length" variant="warn" :tooltip="tip(lowEvidence)">⚠ 근거 불충분 {{ lowEvidence.length }}</RpBadge>
          <RpBadge v-if="otherWarnings.length" variant="warn" :tooltip="tip(otherWarnings)">⚠ 경고 {{ otherWarnings.length }}</RpBadge>
        </template>
        <RpBadge v-else variant="warn" tooltip="이 실행에는 검증 결과가 없습니다.">⚠ 검증 결과 없음</RpBadge>
        <RpBadge v-if="overHist.length" variant="warn" :tooltip="overHistTip">과거 최대 변동폭 초과</RpBadge>
      </div>
    </div>
    <div class="flex-1" />
    <RpButton variant="secondary" :disabled="!run.report" @click="$emit('download')">보고서 다운로드</RpButton>
    <RpButton variant="outline" :disabled="rerunPending" @click="$emit('rerun')">↻ 다시 실행</RpButton>
  </div>
</template>
