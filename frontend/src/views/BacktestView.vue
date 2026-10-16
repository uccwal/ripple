<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { BacktestSummary } from '@/api/types'
import { api, errorMessage } from '@/api/client'
import CalcNum from '@/components/common/CalcNum.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import RpButton from '@/components/common/RpButton.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import type { LoadState } from '@/stores/types'
import { formatDate } from '@/utils/format'

/** 사후 검증 (/backtest): 발표 후 분석 기간이 지난 이벤트 분석의 추정 vs 실제 */
const router = useRouter()
const data = ref<BacktestSummary | null>(null)
const state = ref<LoadState>('idle')
const error = ref<string | null>(null)

async function load(): Promise<void> {
  state.value = 'loading'
  error.value = null
  try {
    data.value = await api.backtest(200)
    state.value = 'ready'
  } catch (err) {
    error.value = errorMessage(err)
    state.value = 'error'
  }
}

const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`)
const kpis = computed(() => {
  const d = data.value
  if (!d) return []
  return [
    { label: '검증 완료 분석', value: `${d.n_cases}건`, sub: '발표 후 분석 기간 경과' },
    { label: '포트폴리오 방향 적중률', value: pct(d.direction_hit_rate), sub: `${d.n_judged}건 판정 (±0.1% 안은 보류)` },
    { label: '충격 변수 방향 적중률', value: pct(d.factor_hit_rate), sub: '시나리오 충격 부호 = 실제 부호' },
    { label: '평균 손익 오차', value: d.mean_abs_error == null ? '—' : `${d.mean_abs_error.toFixed(1)}%p`, sub: '|추정 − 실제|' },
  ]
})

const GRID = 'grid-cols-[110px_minmax(0,1fr)_72px_90px_90px_80px_96px_80px]'

function open(id: string): void {
  void router.push({ name: 'run', params: { id }, query: { tab: 'result' } })
}

onMounted(() => void load())
</script>

<template>
  <div class="mx-auto flex max-w-[1440px] flex-col gap-4 px-8 pb-12 pt-7">
    <div>
      <h1 class="m-0 text-title font-bold tracking-[-0.02em]">사후 검증</h1>
      <div class="text-small text-ink-3">
        발표 전 마지막 거래일 종가 기준으로 분석 기간이 지난 이벤트 분석을 실제 시장 움직임과 비교합니다. 숫자는 모두 엔진이 계산하며 숨기지 않습니다.
      </div>
    </div>

    <ErrorState v-if="state === 'error'" title="사후 검증 결과를 불러오지 못했습니다" :message="error" @retry="load()" />

    <template v-else>
      <div class="grid grid-cols-4 gap-4">
        <section v-for="k in kpis" :key="k.label" class="rp-card px-5 py-[18px]">
          <h2 class="m-0 text-small font-bold text-ink-2">{{ k.label }}</h2>
          <div class="tnum mt-1.5 text-[28px] font-bold leading-[1.4]">{{ k.value }}</div>
          <div class="mt-1 text-caption text-ink-3">{{ k.sub }}</div>
        </section>
        <template v-if="state !== 'ready'">
          <section v-for="i in 4" :key="`s${i}`" class="rp-card flex flex-col gap-2 px-5 py-[18px]" aria-hidden="true">
            <SkeletonBar w="60%" :h="12" /><SkeletonBar w="40%" :h="28" tone="strong" :radius="4" />
          </section>
        </template>
      </div>

      <EmptyState
        v-if="state === 'ready' && data && data.cases.length === 0"
        title="아직 검증할 수 있는 분석이 없습니다"
        description="발표일이 20영업일 이상 지난 정책 이벤트를 분석하면 이 표에 추정 vs 실제가 쌓입니다. 과거 이벤트를 하나 분석해 보세요."
      >
        <RpButton :to="{ name: 'events' }">정책 이벤트로</RpButton>
      </EmptyState>

      <div v-else-if="data" class="rp-card overflow-hidden" role="table" aria-label="사후 검증 사례">
        <div class="rp-thead grid gap-3 px-5 py-2.5" :class="GRID" role="row">
          <span>발표일</span><span>이벤트</span><span>포트폴리오</span>
          <span class="text-right">추정 손익</span><span class="text-right">실제 손익</span><span class="text-right">오차</span>
          <span>방향</span><span class="text-right">팩터 적중</span>
        </div>
        <div
          v-for="c in data.cases"
          :key="c.run_id"
          class="tnum grid cursor-pointer items-center gap-3 border-t border-line-subtle px-5 py-2.5 text-small hover:bg-bg"
          :class="GRID"
          role="row"
          tabindex="0"
          @click="open(c.run_id)"
          @keydown.enter="open(c.run_id)"
        >
          <span class="text-ink-2">{{ formatDate(c.announced_at) }}</span>
          <span class="ellipsis font-semibold" :title="c.title">{{ c.title }}</span>
          <span class="font-mono text-[12px] text-ink-3">{{ c.portfolio_id }}</span>
          <CalcNum class="text-right font-bold" :value="c.estimate_pnl" :interactive="false" />
          <CalcNum class="text-right font-bold" :value="c.actual_pnl" :interactive="false" />
          <span class="text-right text-ink-2">{{ c.abs_error == null ? '—' : `${c.abs_error.toFixed(1)}%p` }}</span>
          <span>
            <RpBadge v-if="c.direction_hit === true" variant="pass">적중</RpBadge>
            <RpBadge v-else-if="c.direction_hit === false" variant="warn">불일치</RpBadge>
            <RpBadge v-else variant="outline">보류</RpBadge>
          </span>
          <span class="text-right">{{ pct(c.factor_hit_rate) }}</span>
        </div>
      </div>
    </template>
  </div>
</template>
