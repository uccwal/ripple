<script setup lang="ts">
import { computed } from 'vue'
import type { SeriesRole, SeriesStatus } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import { formatDateRange, formatInt } from '@/utils/dataStatus'
import { formatDateTime } from '@/utils/format'
import { SERIES_QUALITY_BADGE, SERIES_ROLE_LABEL } from '@/utils/labels'

/** S7 시계열 표: 팩터 → 자산 → 보조 순, 사용하지 않는 시리즈는 흐리게 */
const props = defineProps<{ series: SeriesStatus[] }>()

const GRID = 'grid-cols-[110px_minmax(0,1.1fr)_60px_minmax(0,1.2fr)_190px_72px_128px_120px]'
const ROLE_ORDER: Record<SeriesRole, number> = { factor: 0, asset: 1, other: 2 }

const rows = computed(() =>
  [...props.series].sort(
    (a, b) =>
      ROLE_ORDER[a.role] - ROLE_ORDER[b.role] ||
      Number(b.in_use) - Number(a.in_use) ||
      a.series_id.localeCompare(b.series_id),
  ),
)

const counts = computed(() => {
  const real = props.series.filter((s) => !s.synthetic).length
  const issues = props.series.filter((s) => s.in_use && (s.quality === 'stale' || s.quality === 'gappy' || s.quality === 'empty')).length
  return { total: props.series.length, real, synthetic: props.series.length - real, issues }
})

/** 상태 칸 보조 문구: 지연 영업일·커버리지 */
function qualityDetail(s: SeriesStatus): string {
  const parts: string[] = []
  if (s.stale_bdays != null && s.stale_bdays > 0) parts.push(`${s.stale_bdays}영업일 전`)
  if (s.coverage != null) parts.push(`커버리지 ${Math.round(s.coverage * 100)}%`)
  return parts.join(' · ')
}
</script>

<template>
  <section class="rp-card overflow-hidden" role="table" aria-label="시계열">
    <div class="flex items-baseline gap-3 px-5 py-3">
      <h2 class="m-0 text-body font-bold">시계열</h2>
      <span v-if="counts.total" class="tnum text-caption text-ink-3">
        {{ counts.total }}개 · 실데이터 {{ counts.real }} · 합성 {{ counts.synthetic }}<template v-if="counts.issues"> · 점검 필요 {{ counts.issues }}</template>
      </span>
    </div>

    <div v-if="series.length === 0" class="px-5 pb-5">
      <EmptyState compact title="등록된 시계열이 없습니다" description="수집기를 실행하거나 data/ 의 시드를 적재한 뒤 다시 확인하세요." />
    </div>

    <template v-else>
      <div class="rp-thead grid gap-4 px-5 py-2.5" :class="GRID" role="row">
        <span role="columnheader">시리즈</span>
        <span role="columnheader">이름</span>
        <span role="columnheader">역할</span>
        <span role="columnheader">출처</span>
        <span role="columnheader">기간</span>
        <span role="columnheader" class="text-right">건수</span>
        <span role="columnheader">최종 수집</span>
        <span role="columnheader">상태</span>
      </div>

      <div
        v-for="s in rows"
        :key="s.series_id"
        class="grid items-center gap-4 border-t border-line-subtle px-5 py-2.5 text-small"
        :class="[GRID, s.in_use ? '' : 'text-ink-3']"
        role="row"
        :title="s.in_use ? undefined : '현재 팩터·포트폴리오 계산에 쓰이지 않는 시리즈'"
      >
        <span class="font-mono text-[12px]" :class="s.in_use ? 'text-ink' : ''">{{ s.series_id }}</span>
        <span class="min-w-0">
          <span class="ellipsis block font-semibold" :title="s.name">{{ s.name }}</span>
          <span class="ellipsis block text-micro" :class="s.in_use ? 'text-ink-3' : ''">
            {{ s.unit }}<template v-if="s.factor_name && s.factor_name !== s.name"> · 팩터 {{ s.factor_name }}</template>
          </span>
        </span>
        <span><RpBadge variant="entry">{{ SERIES_ROLE_LABEL[s.role] }}</RpBadge></span>
        <span class="min-w-0">
          <span class="ellipsis block" :class="s.in_use ? 'text-ink-2' : ''" :title="s.source">
            <a v-if="s.source_url" :href="s.source_url" target="_blank" rel="noopener noreferrer" class="font-medium">{{ s.source }} ↗</a>
            <template v-else>{{ s.source }}</template>
          </span>
          <span v-if="s.license" class="ellipsis block text-micro" :class="s.in_use ? 'text-ink-3' : ''" :title="s.license">{{ s.license }}</span>
        </span>
        <span class="tnum" :class="s.in_use ? 'text-ink-2' : ''">{{ formatDateRange(s.first_date, s.last_date) }}</span>
        <span class="tnum text-right font-semibold">{{ formatInt(s.count) }}</span>
        <span class="tnum" :class="s.in_use ? 'text-ink-2' : ''">{{ formatDateTime(s.collected_at) }}</span>
        <span class="min-w-0">
          <RpBadge :variant="SERIES_QUALITY_BADGE[s.quality].variant" :tooltip="SERIES_QUALITY_BADGE[s.quality].tip">
            {{ SERIES_QUALITY_BADGE[s.quality].text }}
          </RpBadge>
          <span v-if="!s.synthetic && qualityDetail(s)" class="tnum mt-0.5 block text-micro" :class="s.in_use ? 'text-ink-3' : ''">
            {{ qualityDetail(s) }}
          </span>
        </span>
      </div>
    </template>
  </section>
</template>
