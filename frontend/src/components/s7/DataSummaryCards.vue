<script setup lang="ts">
import { computed } from 'vue'
import type { DataStatus } from '@/api/types'
import RpBadge from '@/components/common/RpBadge.vue'
import RpSpinner from '@/components/common/RpSpinner.vue'
import { formatDailyKst, formatKst, formatRelative } from '@/utils/dataStatus'
import { LLM_MODE_LABEL, SYNTHETIC_SERIES_TIP } from '@/utils/labels'

/** S7 상단 요약 카드 4개: 데이터 상태 · LLM · 마지막 수집 · 다음 예약 수집 */
const props = defineProps<{ status: DataStatus; now: number }>()

const synthetic = computed(() => props.status.synthetic_remaining)

const errorCount = computed(() => {
  const c = props.status.collect
  return c.reports.filter((r) => r.status === 'error').length + (c.error ? 1 : 0)
})

const lastRun = computed(() => {
  const c = props.status.collect
  if (c.running) return { kind: 'running' as const, since: formatRelative(c.started_at, props.now), title: formatKst(c.started_at) }
  if (!c.finished_at) return { kind: 'none' as const }
  return { kind: 'done' as const, rel: formatRelative(c.finished_at, props.now), title: formatKst(c.finished_at) }
})

const next = computed(() => {
  const c = props.status.collect
  const daily = formatDailyKst(props.status.daily_hour_utc)
  if (c.next_scheduled_at) return { value: formatKst(c.next_scheduled_at), sub: daily ?? formatRelative(c.next_scheduled_at, props.now), off: false }
  if (daily) return { value: daily, sub: '다음 예약 시각은 서버가 첫 수집을 마친 뒤 정해집니다', off: false }
  return { value: '자동 수집 꺼짐', sub: 'COLLECT_DAILY_HOUR_UTC 미설정', off: true }
})
</script>

<template>
  <div class="grid grid-cols-4 gap-4">
    <section class="rp-card flex flex-col px-5 py-[18px]">
      <h2 class="m-0 text-small font-bold text-ink-2">데이터 상태</h2>
      <div class="mt-2.5 flex items-center">
        <RpBadge v-if="synthetic.length === 0" variant="pass" tall>✓ 실데이터</RpBadge>
        <RpBadge v-else variant="warn" tall :tooltip="SYNTHETIC_SERIES_TIP">⚠ 합성 데이터 {{ synthetic.length }}개 시리즈</RpBadge>
      </div>
      <div v-if="synthetic.length" class="ellipsis mt-2 font-mono text-micro text-ink-3" :title="synthetic.join(', ')">
        {{ synthetic.join(' · ') }}
      </div>
      <div v-else class="mt-2 text-caption text-ink-3">사용 중인 모든 시계열이 수집된 실데이터입니다</div>
    </section>

    <section class="rp-card flex flex-col px-5 py-[18px]">
      <h2 class="m-0 text-small font-bold text-ink-2">LLM</h2>
      <div class="mt-1.5 text-[18px] font-bold leading-[27px]" :class="status.llm_mode === 'offline' ? 'text-ink-2' : ''">
        {{ LLM_MODE_LABEL[status.llm_mode] }}
      </div>
      <div class="ellipsis mt-1.5 font-mono text-micro text-ink-3" :title="`기본 ${status.model_default} · Impact Mapper ${status.model_impact_mapper}`">
        {{ status.model_default }}
      </div>
    </section>

    <section class="rp-card flex flex-col px-5 py-[18px]">
      <h2 class="m-0 text-small font-bold text-ink-2">마지막 수집</h2>
      <template v-if="lastRun.kind === 'running'">
        <div class="mt-1.5 flex items-center gap-2 text-[18px] font-bold leading-[27px] text-navy-900">
          <RpSpinner :size="14" />수집 중
        </div>
        <div class="mt-1.5 text-caption text-ink-3" :title="lastRun.title">시작 {{ lastRun.since }}</div>
      </template>
      <template v-else-if="lastRun.kind === 'none'">
        <div class="mt-1.5 text-[18px] font-bold leading-[27px] text-ink-3">기록 없음</div>
        <div class="mt-1.5 text-caption text-ink-3">서버 기동 후 실행된 수집이 없습니다</div>
      </template>
      <template v-else>
        <div class="mt-1.5 flex items-center gap-2.5">
          <span class="tnum text-[18px] font-bold leading-[27px]" :title="lastRun.title">{{ lastRun.rel }}</span>
          <RpBadge v-if="errorCount" variant="fail">! 오류 {{ errorCount }}건</RpBadge>
          <RpBadge v-else variant="pass">✓ 정상</RpBadge>
        </div>
        <div class="tnum mt-1.5 text-caption text-ink-3">{{ lastRun.title }}</div>
      </template>
    </section>

    <section class="rp-card flex flex-col px-5 py-[18px]">
      <h2 class="m-0 text-small font-bold text-ink-2">다음 예약 수집</h2>
      <div class="tnum mt-1.5 text-[18px] font-bold leading-[27px]" :class="next.off ? 'text-ink-3' : ''">{{ next.value }}</div>
      <div class="ellipsis mt-1.5 text-caption text-ink-3" :title="next.sub">{{ next.sub }}</div>
    </section>
  </div>
</template>
