<script setup lang="ts">
import { computed } from 'vue'
import type { AssetResult, RunState } from '@/api/types'
import CalcNum from '@/components/common/CalcNum.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { useUiStore } from '@/stores/ui'
import { formatPct, formatRange, formatWeight, pnlColor } from '@/utils/format'
import ActualCard from './ActualCard.vue'
import AssetPnlBars from './AssetPnlBars.vue'
import CrossPortfolioCard from './CrossPortfolioCard.vue'

const props = defineProps<{ run: RunState }>()
const ui = useUiStore()

const result = computed(() => props.run.result)

/** 손실 기여 상위 5: top_contributors 순서를 따르고, 없으면 기여도 오름차순 */
const top5 = computed<AssetResult[]>(() => {
  const r = result.value
  if (!r) return []
  const byId = new Map(r.by_asset.map((a) => [a.asset_id, a]))
  const listed = r.top_contributors.map((id) => byId.get(id)).filter((a): a is AssetResult => !!a)
  const base = listed.length ? listed : [...r.by_asset].sort((a, b) => a.contribution - b.contribution)
  return base.slice(0, 5)
})

const regimes = computed(() => [...props.run.regimes].sort((a, b) => b.similarity - a.similarity))

function openAsset(id: string): void {
  ui.openCalc(props.run.run_id, `h:${id}`)
}
</script>

<template>
  <EmptyState
    v-if="!result"
    title="계산 결과가 없습니다"
    description="Risk Engine 단계가 완료되지 않았습니다. 실행 과정에서 실패한 단계를 확인하세요."
  />
  <template v-else>
    <div class="grid grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] items-start gap-4">
      <section class="rp-card px-5 py-4">
        <div class="mb-3 flex items-baseline justify-between">
          <h3 class="m-0 text-body font-bold">자산별 손익</h3>
          <span class="text-caption font-normal text-ink-3">손실 큰 순 · 자산 수익률 ΔR</span>
        </div>
        <AssetPnlBars :run-id="run.run_id" :assets="result.by_asset" />
      </section>

      <div class="flex flex-col gap-4">
        <div class="grid grid-cols-2 gap-3">
          <section class="rp-card px-4 py-3.5">
            <div class="text-caption font-normal text-ink-3">팩터 모델 추정</div>
            <CalcNum class="text-2xl font-bold" :value="result.portfolio_pnl" :run-id="run.run_id" calc-key="model" :offset="4" label="팩터 모델 추정" />
            <div class="tnum text-caption font-normal text-ink-2">
              범위
              <CalcNum :text="formatRange(result.range.low, result.range.high)" :run-id="run.run_id" calc-key="range" tone="inherit" label="추정 범위" />
            </div>
          </section>
          <section class="rp-card px-4 py-3.5">
            <div class="text-caption font-normal text-ink-3">과거 유사 국면 추정</div>
            <template v-if="result.regime_estimate">
              <CalcNum
                class="text-2xl font-bold"
                :value="result.regime_estimate.median"
                :run-id="run.run_id"
                calc-key="reg"
                :offset="4"
                label="과거 유사 국면 추정"
              />
              <div class="tnum text-caption font-normal text-ink-2">
                {{ result.regime_estimate.n }}개 구간 중앙값 · {{ formatRange(result.regime_estimate.low, result.regime_estimate.high) }}
              </div>
            </template>
            <div v-else class="mt-1 text-small text-ink-3">유사 국면을 찾지 못했습니다</div>
          </section>
        </div>

        <section class="rp-card overflow-hidden">
          <h3 class="m-0 px-4 py-3 text-body font-bold">손실 기여 상위 5</h3>
          <div class="rp-thead grid grid-cols-[minmax(0,1fr)_56px_64px_72px] gap-2.5 px-4 py-1.5">
            <span>자산</span><span class="text-right">비중</span><span class="text-right">손익</span><span class="text-right">기여도</span>
          </div>
          <button
            v-for="a in top5"
            :key="a.asset_id"
            type="button"
            class="tnum grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_56px_64px_72px] gap-2.5 border-0 border-t border-solid border-line-subtle bg-transparent px-4 py-2 text-left text-small hover:bg-bg"
            @click="openAsset(a.asset_id)"
          >
            <span class="ellipsis">{{ a.name }}</span>
            <span class="text-right text-ink-2">{{ formatWeight(a.weight) }}</span>
            <span class="text-right" :style="{ color: pnlColor(a.ret, 1) }">{{ formatPct(a.ret) }}</span>
            <CalcNum class="text-right font-bold" :value="a.contribution" unit="%p" :interactive="false" />
          </button>
        </section>
      </div>
    </div>

    <div v-if="result.actual || (result.cross_portfolio?.length ?? 0) > 1" class="grid grid-cols-2 items-start gap-4">
      <ActualCard v-if="result.actual" :run="run" :actual="result.actual" />
      <CrossPortfolioCard v-if="(result.cross_portfolio?.length ?? 0) > 1" :run-id="run.run_id" :rows="result.cross_portfolio" />
    </div>

    <section class="rp-card overflow-hidden">
      <div class="flex items-baseline justify-between px-5 py-3">
        <h3 class="m-0 text-body font-bold">과거 유사 국면</h3>
        <span class="text-caption font-normal text-ink-3">{{ run.horizon_days }}영업일 롤링 구간 · 팩터 변화 벡터 코사인 유사도</span>
      </div>
      <div class="rp-thead grid grid-cols-[220px_minmax(0,1fr)_220px_120px] gap-4 px-5 py-1.5">
        <span>기간</span><span>당시 국면</span><span>유사도</span><span class="text-right">당시 실제 손익</span>
      </div>
      <div
        v-for="g in regimes"
        :key="g.start"
        class="tnum grid grid-cols-[220px_minmax(0,1fr)_220px_120px] items-center gap-4 border-t border-line-subtle px-5 py-[9px] text-small"
      >
        <span>{{ g.start }} ~ {{ g.end }}</span>
        <span class="ellipsis" :class="g.tag ? 'font-semibold text-ink' : 'text-ink-3'" :title="g.tag || g.summary">{{ g.tag || g.summary || '—' }}</span>
        <div class="flex items-center gap-2">
          <div class="h-1.5 flex-1 rounded-xs bg-line-subtle">
            <div class="h-1.5 rounded-xs bg-navy-500" :style="{ width: `${Math.max(0, Math.min(1, g.similarity)) * 100}%` }" />
          </div>
          <span class="w-8">{{ g.similarity.toFixed(2) }}</span>
        </div>
        <CalcNum class="justify-self-end font-bold" :value="g.pnl" :run-id="run.run_id" calc-key="reg" label="당시 실제 손익" />
      </div>
      <div v-if="regimes.length === 0" class="border-t border-line-subtle px-5 py-4 text-small text-ink-3">유사 국면이 없습니다.</div>
    </section>
  </template>
</template>
