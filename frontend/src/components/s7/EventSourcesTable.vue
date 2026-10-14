<script setup lang="ts">
import { computed } from 'vue'
import type { EventSourceStatus } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import { formatDateRange, formatInt } from '@/utils/dataStatus'

/** S7 정책 이벤트 출처 표: 수집된 출처 먼저, 예시는 뒤로 */
const props = defineProps<{ events: EventSourceStatus[] }>()

const GRID = 'grid-cols-[minmax(0,1fr)_72px_64px_200px]'

const rows = computed(() =>
  [...props.events].sort((a, b) => Number(a.is_demo) - Number(b.is_demo) || b.count - a.count || a.source.localeCompare(b.source)),
)

const total = computed(() => props.events.reduce((n, e) => n + e.count, 0))
const demo = computed(() => props.events.filter((e) => e.is_demo).reduce((n, e) => n + e.count, 0))
</script>

<template>
  <section class="rp-card overflow-hidden" role="table" aria-label="정책 이벤트 출처">
    <div class="flex items-baseline gap-3 px-5 py-3">
      <h2 class="m-0 text-body font-bold">정책 이벤트</h2>
      <span v-if="total" class="tnum text-caption text-ink-3">{{ formatInt(total) }}건<template v-if="demo"> · 예시 {{ formatInt(demo) }}건</template></span>
    </div>

    <div v-if="events.length === 0" class="px-5 pb-5">
      <EmptyState compact title="수집된 정책 이벤트가 없습니다" description="federal_register · korea_briefing 수집기를 실행하면 채워집니다." />
    </div>

    <template v-else>
      <div class="rp-thead grid gap-4 px-5 py-2.5" :class="GRID" role="row">
        <span role="columnheader">출처</span>
        <span role="columnheader">구분</span>
        <span role="columnheader" class="text-right">건수</span>
        <span role="columnheader">기간</span>
      </div>
      <div
        v-for="e in rows"
        :key="`${e.source}:${e.is_demo}`"
        class="grid items-center gap-4 border-t border-line-subtle px-5 py-2.5 text-small"
        :class="GRID"
        role="row"
      >
        <span class="ellipsis font-semibold" :title="e.source">{{ e.source }}</span>
        <span>
          <RpBadge v-if="e.is_demo" variant="virtual" tooltip="시연용 예시 이벤트 — 실제 정책 발표가 아닙니다">예시</RpBadge>
          <RpBadge v-else variant="entry">수집</RpBadge>
        </span>
        <span class="tnum text-right font-semibold">{{ formatInt(e.count) }}</span>
        <span class="tnum text-ink-2">{{ formatDateRange(e.first_date, e.last_date) }}</span>
      </div>
    </template>
  </section>
</template>
