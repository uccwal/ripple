<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import type { Holding } from '@/api/types'
import ErrorState from '@/components/common/ErrorState.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import DonutCard from '@/components/s4/DonutCard.vue'
import { usePortfolioStore } from '@/stores/portfolios'
import { formatAum, formatWeight } from '@/utils/format'

/** S4 포트폴리오 (/portfolios) */
const store = usePortfolioStore()
const { list, listState, listError, selectedId, selected, holdings, detailState, detailError } = storeToRefs(store)

const GRID = 'grid-cols-[minmax(0,1.4fr)_100px_80px_120px_90px_minmax(0,1fr)]'

function group(key: keyof Pick<Holding, 'asset_class' | 'currency' | 'sector'>) {
  const m = new Map<string, number>()
  for (const h of holdings.value) m.set(h[key], (m.get(h[key]) ?? 0) + h.weight)
  return [...m].map(([label, weight]) => ({ label, weight }))
}

const donuts = computed(() => [
  { title: '자산군', items: group('asset_class') },
  { title: '통화', items: group('currency') },
  { title: '업종', items: group('sector') },
])

const rows = computed(() => {
  const sorted = [...holdings.value].sort((a, b) => b.weight - a.weight)
  const max = Math.max(0.01, ...sorted.map((h) => h.weight))
  return sorted.map((h) => ({ ...h, bar: `${(h.weight / max) * 100}%` }))
})

const metaText = computed(() => {
  const p = selected.value
  if (!p) return ''
  const parts = [`기준통화 ${p.base_currency}`, `운용자산 ${formatAum(p.aum)} 상당`, `${p.holdings.length}개 자산`]
  if (p.description) parts.push(p.description)
  return parts.join(' · ')
})

const loading = computed(() => listState.value !== 'error' && (listState.value !== 'ready' || (selectedId.value && detailState.value !== 'ready' && detailState.value !== 'error')))

watch(selectedId, (id) => id && void store.loadDetail(id), { immediate: true })
onMounted(() => {
  if (listState.value !== 'ready') void store.loadList()
})
</script>

<template>
  <div class="mx-auto flex max-w-[1440px] flex-col gap-4 px-8 pb-12 pt-7">
    <div class="flex items-center gap-3">
      <h1 class="m-0 text-title font-bold tracking-[-0.02em]">포트폴리오</h1>
      <RpBadge variant="virtual" tall>가상 포트폴리오 · 실제 기관 보유내역 아님</RpBadge>
      <select
        v-if="listState === 'ready' && list.length"
        class="rp-select ml-auto h-9 min-w-[300px] px-2.5 text-body"
        :value="selectedId ?? ''"
        aria-label="포트폴리오 선택"
        @change="store.select(($event.target as HTMLSelectElement).value)"
      >
        <option v-for="p in list" :key="p.portfolio_id" :value="p.portfolio_id">{{ p.name }}</option>
      </select>
    </div>

    <ErrorState v-if="listState === 'error'" title="포트폴리오 목록을 불러오지 못했습니다" :message="listError" @retry="store.loadList()" />
    <EmptyState v-else-if="listState === 'ready' && list.length === 0" title="등록된 포트폴리오가 없습니다" description="data/ 의 가상 포트폴리오를 시드한 뒤 다시 확인하세요." />
    <ErrorState
      v-else-if="detailState === 'error'"
      title="포트폴리오 구성을 불러오지 못했습니다"
      :message="detailError"
      @retry="selectedId && store.loadDetail(selectedId)"
    />

    <template v-else-if="loading">
      <SkeletonBar w="420px" :h="12" />
      <div class="grid grid-cols-3 gap-4" aria-hidden="true">
        <div v-for="i in 3" :key="i" class="rp-card flex items-center gap-5 px-5 py-[18px]">
          <SkeletonBar w="132px" :h="132" tone="block" :radius="66" />
          <div class="flex flex-1 flex-col gap-2"><SkeletonBar v-for="j in 4" :key="j" :h="12" /></div>
        </div>
      </div>
      <div class="rp-card flex flex-col gap-3 p-5" aria-hidden="true"><SkeletonBar v-for="j in 6" :key="j" :h="14" /></div>
    </template>

    <template v-else-if="selected">
      <div class="-mt-2 text-small text-ink-3">{{ metaText }}</div>
      <div class="grid grid-cols-3 gap-4">
        <DonutCard v-for="d in donuts" :key="d.title" :title="d.title" :items="d.items" />
      </div>
      <section class="rp-card overflow-hidden">
        <h2 class="m-0 px-5 py-3 text-body font-bold">보유 비중</h2>
        <div class="rp-thead grid gap-4 px-5 py-2" :class="GRID">
          <span>자산</span><span>자산군</span><span>통화</span><span>업종</span><span class="text-right">비중</span><span />
        </div>
        <div v-for="h in rows" :key="h.asset_id" class="grid items-center gap-4 border-t border-line-subtle px-5 py-2.5 text-small" :class="GRID">
          <span class="ellipsis font-semibold">{{ h.name }}</span>
          <span class="text-ink-2">{{ h.asset_class }}</span>
          <span class="font-mono text-[12px] text-ink-2">{{ h.currency }}</span>
          <span class="text-ink-2">{{ h.sector }}</span>
          <span class="tnum text-right font-bold">{{ formatWeight(h.weight) }}</span>
          <div class="h-1.5 rounded-xs bg-line-subtle"><div class="h-1.5 rounded-xs bg-navy-500" :style="{ width: h.bar }" /></div>
        </div>
      </section>
    </template>
  </div>
</template>
