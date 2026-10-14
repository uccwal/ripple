<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import RpButton from '@/components/common/RpButton.vue'
import EventCard from '@/components/s1/EventCard.vue'
import EventCardSkeleton from '@/components/s1/EventCardSkeleton.vue'
import EventFilters from '@/components/s1/EventFilters.vue'
import RecentRunsCard from '@/components/s1/RecentRunsCard.vue'
import TodaySummaryCard from '@/components/s1/TodaySummaryCard.vue'
import { useEventStore } from '@/stores/events'
import { useHistoryStore } from '@/stores/history'
import { useMetaStore } from '@/stores/meta'
import { formatDateTime } from '@/utils/format'

/** S1 이벤트 대시보드 (/) */
const eventStore = useEventStore()
const { filters, events, state, error } = storeToRefs(eventStore)
const { meta } = storeToRefs(useMetaStore())
const history = useHistoryStore()

const subtitle = computed(() => {
  const base = '최근 수집된 정책 발표를 보고 분석을 시작합니다'
  return meta.value?.last_collected_at ? `${base} · 마지막 수집 ${formatDateTime(meta.value.last_collected_at)}` : base
})

onMounted(() => {
  void eventStore.fetchEvents()
  void history.load()
})
</script>

<template>
  <div class="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)_320px] gap-6 px-8 pb-12 pt-7">
    <div class="flex min-w-0 flex-col gap-4">
      <div class="flex items-end justify-between gap-4">
        <div>
          <h1 class="m-0 text-title font-bold tracking-[-0.02em]">정책 이벤트</h1>
          <div class="text-small text-ink-3">{{ subtitle }}</div>
        </div>
      </div>

      <EventFilters v-model="filters" />

      <ErrorState v-if="state === 'error'" title="정책 이벤트를 불러오지 못했습니다" :message="error" @retry="eventStore.fetchEvents()" />

      <EmptyState
        v-else-if="state === 'ready' && events.length === 0"
        title="조건에 맞는 정책 이벤트가 없습니다"
        description="필터를 바꾸거나 시나리오를 직접 입력해 분석할 수 있습니다."
      >
        <RpButton :to="{ name: 'new', query: { entry: 'scenario' } }">새 분석</RpButton>
      </EmptyState>

      <div v-else class="grid grid-cols-2 gap-4" :aria-busy="state === 'loading'">
        <template v-if="state === 'ready'">
          <EventCard v-for="e in events" :key="e.event_id" :event="e" />
        </template>
        <template v-else>
          <EventCardSkeleton v-for="i in 4" :key="i" />
        </template>
      </div>
    </div>

    <aside class="flex flex-col gap-4">
      <TodaySummaryCard />
      <RecentRunsCard />
    </aside>
  </div>
</template>
