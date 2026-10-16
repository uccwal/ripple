<script setup lang="ts">
import { computed } from 'vue'
import type { CrossPortfolioRow } from '@/api/types'
import CalcNum from '@/components/common/CalcNum.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import { formatAum, formatEok } from '@/utils/format'
import { useUiStore } from '@/stores/ui'

/** 같은 충격값을 모든 모델 포트폴리오에 적용한 손익 비교 (엔진만, 유사 국면 비교 제외) */
const props = defineProps<{ runId: string; rows: CrossPortfolioRow[] }>()
const ui = useUiStore()
/** 근거 패널 항목(xp)은 손익이 계산된 포트폴리오가 2개 이상일 때만 만들어진다 */
const hasEntry = computed(() => props.rows.filter((r) => r.pnl != null).length > 1)
</script>

<template>
  <section class="rp-card overflow-hidden">
    <div class="flex items-baseline justify-between px-5 py-3">
      <h3 class="m-0 text-body font-bold">포트폴리오 비교</h3>
      <button v-if="hasEntry" type="button" class="cursor-pointer border-0 bg-transparent p-0 text-caption font-normal text-navy-900 hover:underline" @click="ui.openCalc(runId, 'xp')">
        같은 시나리오 · 계산 근거
      </button>
      <span v-else class="text-caption font-normal text-ink-3">같은 시나리오</span>
    </div>
    <div class="rp-thead grid grid-cols-[minmax(0,1fr)_112px_72px_96px] gap-2.5 px-5 py-1.5">
      <span>포트폴리오</span><span class="text-right">운용자산</span><span class="text-right">예상 손익</span><span class="text-right">금액</span>
    </div>
    <div
      v-for="p in rows"
      :key="p.portfolio_id"
      class="tnum grid grid-cols-[minmax(0,1fr)_112px_72px_96px] items-center gap-2.5 border-t border-line-subtle px-5 py-[8px] text-small"
      :class="p.current ? 'bg-navy-50/40' : ''"
    >
      <span class="flex min-w-0 flex-col">
        <span class="flex min-w-0 items-center gap-1.5">
          <span class="ellipsis font-semibold">{{ p.name }}</span>
          <RpBadge v-if="p.current" variant="entry">현재</RpBadge>
        </span>
        <span v-if="p.worst_asset && !p.error" class="ellipsis text-micro text-ink-3" :title="`최대 손실 기여: ${p.worst_asset}`">최대 손실 기여 · {{ p.worst_asset }}</span>
      </span>
      <span class="whitespace-nowrap text-right text-ink-2">{{ formatAum(p.aum) }}</span>
      <template v-if="p.error">
        <span class="col-span-2 text-right text-micro text-ink-3" :title="p.error">계산 불가</span>
      </template>
      <template v-else>
        <CalcNum class="text-right font-bold" :value="p.pnl" :interactive="false" />
        <span class="text-right text-ink-2">{{ formatEok(p.amount) }}</span>
      </template>
    </div>
  </section>
</template>
