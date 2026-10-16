<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import RpBadge from '@/components/common/RpBadge.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import { useMetaStore } from '@/stores/meta'
import { formatDelta } from '@/utils/format'

/** S1 우측 상단 레이더: 오늘 수집 · 최근 7일 · 자동 분석 · 사후 검증 적중률 · 데이터 상태 */
const metaStore = useMetaStore()
const { meta, state, error } = storeToRefs(metaStore)

const radar = computed(() => meta.value?.radar ?? null)
const hitPct = computed(() => {
  const r = radar.value?.backtest.direction_hit_rate
  return r == null ? null : Math.round(r * 100)
})
const dataOk = computed(() => radar.value != null && radar.value.quality_issues.length === 0 && radar.value.synthetic_remaining.length === 0)
</script>

<template>
  <section class="rp-card px-5 py-[18px]">
    <h2 class="m-0 text-small font-bold text-ink-2">최근 7일 수집된 정책 이벤트</h2>
    <template v-if="meta">
      <div class="mb-3 mt-1.5 flex items-baseline gap-1.5">
        <span class="tnum text-[32px] font-bold leading-[1.5]">{{ radar ? radar.events_7d : meta.today_event_count }}</span>
        <span class="text-small text-ink-3">건 · 오늘 {{ meta.today_event_count }}건 ({{ formatDelta(meta.today_event_delta) }})</span>
      </div>
      <ul v-if="radar && radar.events_7d_by_source.length" class="m-0 flex list-none flex-col gap-1.5 p-0 text-small text-ink-2">
        <li v-for="s in radar.events_7d_by_source" :key="s.source" class="flex justify-between gap-3">
          <span class="ellipsis">{{ s.source }}</span><span class="tnum">{{ s.count }}</span>
        </li>
      </ul>
      <div v-else class="text-small text-ink-3">최근 7일에 수집된 발표가 없습니다.</div>

      <template v-if="radar">
        <div class="mt-4 border-t border-line-subtle pt-3 text-caption font-bold text-ink-3">최근 7일 요약</div>
        <dl class="tnum m-0 mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1.5 text-small">
          <dt class="text-ink-3">관련성 높음 · 한국</dt>
          <dd class="m-0 text-right font-semibold">{{ radar.events_7d_high }}<span class="font-normal text-ink-3"> · {{ radar.events_7d_kr }}</span></dd>
          <dt class="text-ink-3">분석 실행</dt>
          <dd class="m-0 text-right font-semibold">
            {{ radar.runs_7d }}<span class="font-normal text-ink-3"> · 자동 {{ radar.auto_runs_7d }}</span>
          </dd>
          <dt class="text-ink-3" title="발표 후 분석 기간이 지난 이벤트 분석의 포트폴리오 손익 방향 적중률 (사후 검증)">
            <RouterLink :to="{ name: 'backtest' }" class="text-ink-3 no-underline hover:underline">방향 적중률 ↗</RouterLink>
          </dt>
          <dd class="m-0 text-right font-semibold">
            <template v-if="hitPct != null">
              {{ hitPct }}%<span class="font-normal text-ink-3"> · {{ radar.backtest.n_judged }}건</span>
            </template>
            <span v-else class="font-normal text-ink-3">검증 가능한 분석 없음</span>
          </dd>
          <dt class="text-ink-3">데이터</dt>
          <dd class="m-0 flex justify-end">
            <RpBadge v-if="dataOk" variant="pass">✓ 실데이터 · 최신</RpBadge>
            <RpBadge v-else-if="radar.synthetic_remaining.length" variant="warn" :tooltip="radar.synthetic_remaining.join(', ')">⚠ 합성 {{ radar.synthetic_remaining.length }}</RpBadge>
            <RpBadge v-else variant="warn" :tooltip="radar.quality_issues.join(', ')">⚠ 점검 {{ radar.quality_issues.length }}</RpBadge>
          </dd>
        </dl>
      </template>
    </template>
    <div v-else-if="state === 'error'" class="mt-2 flex flex-col items-start gap-2 text-small text-ink-2">
      <span>{{ error }}</span>
      <button type="button" class="cursor-pointer border-0 bg-transparent p-0 text-caption font-semibold text-navy-900" @click="metaStore.load()">
        다시 시도
      </button>
    </div>
    <div v-else class="mt-2 flex flex-col gap-2" aria-hidden="true">
      <SkeletonBar w="64px" :h="32" tone="strong" :radius="4" />
      <SkeletonBar :h="12" />
      <SkeletonBar w="80%" :h="12" />
    </div>
  </section>
</template>
