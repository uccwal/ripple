<script setup lang="ts">
import { computed } from 'vue'
import type { ActualOutcome, RunState } from '@/api/types'
import CalcNum from '@/components/common/CalcNum.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import { formatWithUnit, pnlColor, shockDigits } from '@/utils/format'
import { ACTUAL_TIP } from '@/utils/labels'

/** 사후 검증 — 발표 후 실제 시장 움직임 vs 시나리오·추정 */
const props = defineProps<{ run: RunState; actual: ActualOutcome }>()

const rows = computed(() =>
  Object.entries(props.actual.factors)
    .map(([id, f]) => ({ id, ...f }))
    .sort((a, b) => Number(b.shock != null) - Number(a.shock != null) || Math.abs(b.actual) - Math.abs(a.actual)),
)
const hitPct = computed(() => (props.actual.factor_hit_rate == null ? null : Math.round(props.actual.factor_hit_rate * 100)))
</script>

<template>
  <section class="rp-card overflow-hidden">
    <div class="flex items-center gap-2 px-5 py-3">
      <h3 class="m-0 text-body font-bold">사후 검증 · 실제 시장 움직임</h3>
      <RpBadge v-if="!actual.complete" variant="warn" tooltip="관측 기간이 분석 기간에 못 미칩니다">잠정 {{ actual.days }}/{{ actual.horizon }}일</RpBadge>
      <span class="tnum ml-auto text-caption font-normal text-ink-3" :title="ACTUAL_TIP">{{ actual.start }} → {{ actual.end }}</span>
    </div>

    <div class="grid grid-cols-3 gap-3 px-5 pb-3">
      <div class="rounded bg-bg px-3.5 py-2.5">
        <div class="text-caption font-normal text-ink-3">실제 포트폴리오 손익</div>
        <CalcNum
          v-if="actual.portfolio_pnl != null"
          class="text-xl font-bold"
          :value="actual.portfolio_pnl"
          :run-id="run.run_id"
          calc-key="act"
          :offset="4"
          label="실제 포트폴리오 손익"
        />
        <div v-else class="text-small text-ink-3">자산 데이터 부족</div>
      </div>
      <div class="rounded bg-bg px-3.5 py-2.5">
        <div class="text-caption font-normal text-ink-3">팩터 모델 추정</div>
        <CalcNum class="text-xl font-bold" :value="actual.estimate_pnl" :run-id="run.run_id" calc-key="pnl" :offset="4" label="팩터 모델 추정" />
        <div v-if="actual.abs_error != null" class="tnum text-micro text-ink-3">오차 {{ actual.abs_error.toFixed(1) }}%p</div>
      </div>
      <div class="rounded bg-bg px-3.5 py-2.5">
        <div class="text-caption font-normal text-ink-3">방향</div>
        <div class="mt-1 flex flex-wrap gap-1.5">
          <RpBadge v-if="actual.direction_hit === true" variant="pass">✓ 포트폴리오 적중</RpBadge>
          <RpBadge v-else-if="actual.direction_hit === false" variant="warn">✗ 포트폴리오 불일치</RpBadge>
          <RpBadge v-if="hitPct != null" :variant="hitPct >= 50 ? 'pass' : 'warn'" :tooltip="`충격 변수 ${actual.factors_judged}개 중 부호 일치 비율`">
            팩터 {{ hitPct }}%
          </RpBadge>
        </div>
      </div>
    </div>

    <div class="rp-thead grid grid-cols-[minmax(0,1fr)_96px_96px_72px] gap-2.5 px-5 py-1.5">
      <span>변수</span><span class="text-right">시나리오 충격</span><span class="text-right">실제 변화</span><span class="text-right">방향</span>
    </div>
    <div
      v-for="f in rows"
      :key="f.id"
      class="tnum grid grid-cols-[minmax(0,1fr)_96px_96px_72px] items-center gap-2.5 border-t border-line-subtle px-5 py-[7px] text-small"
      :class="f.shock == null ? 'text-ink-3' : ''"
    >
      <span class="ellipsis">{{ f.name }}</span>
      <span class="text-right">{{ f.shock == null ? '—' : formatWithUnit(f.shock, f.unit, { digits: shockDigits(f.unit) }) }}</span>
      <span class="text-right font-semibold" :style="{ color: pnlColor(f.actual, shockDigits(f.unit)) }">
        {{ formatWithUnit(f.actual, f.unit, { digits: shockDigits(f.unit) }) }}
      </span>
      <span class="text-right">
        <template v-if="f.hit === true"><span class="font-semibold text-pass">적중</span></template>
        <template v-else-if="f.hit === false"><span class="font-semibold text-warn">불일치</span></template>
        <template v-else>—</template>
      </span>
    </div>
    <div class="px-5 py-2.5 text-micro text-ink-3">발표 전 마지막 거래일 종가 기준. 실제 움직임에는 이 이벤트 외의 요인도 섞여 있습니다.</div>
  </section>
</template>
