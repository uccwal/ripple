<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import ErrorState from '@/components/common/ErrorState.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import CollectCard from '@/components/s7/CollectCard.vue'
import CollectorsTable from '@/components/s7/CollectorsTable.vue'
import DataSummaryCards from '@/components/s7/DataSummaryCards.vue'
import EventSourcesTable from '@/components/s7/EventSourcesTable.vue'
import SeriesTable from '@/components/s7/SeriesTable.vue'
import { useDataStore } from '@/stores/data'
import { useUiStore } from '@/stores/ui'

/**
 * S7 데이터 관리 (/data)
 * - 열려 있는 동안 60초마다 상태를 조용히 갱신한다.
 * - 수집이 진행 중이면 3초마다 폴링해 보고서를 실시간으로 보여주고, 끝나면 토스트를 띄운다.
 */
const POLL_MS = 3000
const REFRESH_MS = 60_000

const store = useDataStore()
const ui = useUiStore()
const { status, state, error, refreshError, running } = storeToRefs(store)

/** 상대 시각("12분 전") 계산 기준. 갱신할 때마다 맞춘다. */
const now = ref(Date.now())

let pollTimer: ReturnType<typeof setTimeout> | undefined
let refreshTimer: ReturnType<typeof setInterval> | undefined
/** 수집 진행을 추적 중 (끝나면 토스트) */
let tracking = false
let unmounted = false

async function refresh(opts?: { reset?: boolean }): Promise<void> {
  await store.load(opts)
  now.value = Date.now()
}

function announce(): void {
  const c = status.value?.collect
  if (!c) return
  const errors = c.reports.filter((r) => r.status === 'error').length + (c.error ? 1 : 0)
  ui.showToast(errors ? `수집 완료 · 오류 ${errors}건` : '수집 완료')
}

async function poll(): Promise<void> {
  pollTimer = undefined
  if (unmounted || !tracking) return
  await refresh()
  if (unmounted || !tracking) return
  if (running.value) {
    pollTimer = setTimeout(() => void poll(), POLL_MS)
  } else {
    tracking = false
    announce()
  }
}

/** 수집 시작 직후(또는 진행 중인 수집을 발견했을 때) 폴링을 시작한다. */
function track(delay = POLL_MS): void {
  if (tracking) return
  tracking = true
  clearTimeout(pollTimer)
  pollTimer = setTimeout(() => void poll(), delay)
}

watch(running, (r) => {
  if (r) track()
})

const subtitle = '시계열·정책 이벤트 출처와 수집 현황 · 모든 수치의 근거가 되는 데이터입니다'
const showSkeleton = computed(() => state.value !== 'error' && !status.value)

onMounted(async () => {
  await refresh()
  refreshTimer = setInterval(() => {
    if (!tracking) void refresh()
  }, REFRESH_MS)
})

onUnmounted(() => {
  unmounted = true
  tracking = false
  clearTimeout(pollTimer)
  clearInterval(refreshTimer)
})
</script>

<template>
  <div class="mx-auto flex max-w-[1440px] flex-col gap-4 px-8 pb-12 pt-7">
    <div class="flex items-end justify-between gap-4">
      <div>
        <h1 class="m-0 text-title font-bold tracking-[-0.02em]">데이터</h1>
        <div class="text-small text-ink-3">{{ subtitle }}</div>
      </div>
      <div v-if="status" class="flex items-center gap-3 text-caption text-ink-3">
        <span v-if="refreshError" class="font-semibold text-warn" :title="refreshError">⚠ 갱신 실패 · 60초 후 다시 시도</span>
        <span v-else>60초마다 자동 갱신</span>
        <button
          type="button"
          class="h-[30px] cursor-pointer whitespace-nowrap rounded border border-line-strong bg-white px-3 text-caption font-semibold text-ink hover:border-navy-900 hover:text-navy-900"
          @click="refresh()"
        >
          새로고침
        </button>
      </div>
    </div>

    <ErrorState v-if="state === 'error'" title="데이터 현황을 불러오지 못했습니다" :message="error" @retry="refresh({ reset: true })" />

    <template v-else-if="showSkeleton">
      <div class="grid grid-cols-4 gap-4" aria-hidden="true">
        <div v-for="i in 4" :key="i" class="rp-card flex flex-col gap-3 px-5 py-[18px]">
          <SkeletonBar w="72px" :h="12" />
          <SkeletonBar w="140px" :h="24" tone="strong" :radius="4" />
          <SkeletonBar w="60%" :h="10" />
        </div>
      </div>
      <div class="rp-card overflow-hidden" aria-hidden="true">
        <div class="px-5 py-3"><SkeletonBar w="60px" :h="14" tone="strong" /></div>
        <div class="rp-thead h-9" />
        <div v-for="i in 8" :key="i" class="flex items-center gap-4 border-t border-line-subtle px-5 py-3">
          <SkeletonBar w="80px" :h="12" />
          <SkeletonBar w="22%" :h="12" tone="strong" />
          <SkeletonBar w="44px" :h="22" :radius="4" />
          <SkeletonBar w="24%" :h="12" />
          <SkeletonBar w="160px" :h="12" />
          <SkeletonBar w="48px" :h="12" />
          <SkeletonBar w="110px" :h="12" />
          <SkeletonBar w="72px" :h="22" :radius="4" />
        </div>
      </div>
      <div class="grid grid-cols-[minmax(0,1fr)_400px] items-start gap-4" aria-hidden="true">
        <div class="flex flex-col gap-4">
          <div class="rp-card overflow-hidden">
            <div class="px-5 py-3"><SkeletonBar w="80px" :h="14" tone="strong" /></div>
            <div class="rp-thead h-9" />
            <div v-for="i in 3" :key="i" class="flex items-center gap-4 border-t border-line-subtle px-5 py-3">
              <SkeletonBar w="40%" :h="12" tone="strong" />
              <SkeletonBar w="40px" :h="22" :radius="4" />
              <SkeletonBar w="32px" :h="12" />
              <SkeletonBar w="160px" :h="12" />
            </div>
          </div>
          <div class="rp-card overflow-hidden">
            <div class="px-5 py-3"><SkeletonBar w="56px" :h="14" tone="strong" /></div>
            <div class="rp-thead h-9" />
            <div v-for="i in 5" :key="i" class="flex items-center gap-4 border-t border-line-subtle px-5 py-3">
              <SkeletonBar w="100px" :h="12" tone="strong" />
              <SkeletonBar w="30%" :h="12" />
              <SkeletonBar w="120px" :h="12" />
              <SkeletonBar w="64px" :h="22" :radius="4" />
              <SkeletonBar w="20%" :h="12" />
            </div>
          </div>
        </div>
        <div class="rp-card flex flex-col gap-4 p-5">
          <SkeletonBar w="64px" :h="14" tone="strong" />
          <SkeletonBar :h="36" :radius="6" />
          <SkeletonBar :h="36" :radius="6" />
          <div class="flex gap-2"><SkeletonBar v-for="i in 4" :key="i" w="80px" :h="28" :radius="14" /></div>
          <SkeletonBar w="96px" :h="36" :radius="6" tone="strong" />
        </div>
      </div>
    </template>

    <template v-else-if="status">
      <DataSummaryCards :status="status" :now="now" />
      <SeriesTable :series="status.series" />
      <div class="grid grid-cols-[minmax(0,1fr)_400px] items-start gap-4">
        <div class="flex min-w-0 flex-col gap-4">
          <EventSourcesTable :events="status.events" />
          <CollectorsTable :collectors="status.collectors" :collect="status.collect" />
        </div>
        <CollectCard
          :admin-enabled="status.admin_enabled"
          :collectors="status.collectors"
          :collect="status.collect"
          :now="now"
          @started="track(400)"
        />
      </div>
    </template>
  </div>
</template>
