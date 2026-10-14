<script setup lang="ts">
import { computed } from 'vue'
import type { CollectReport, CollectState, CollectorStatus } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import RpSpinner from '@/components/common/RpSpinner.vue'
import { summarizeCounts } from '@/utils/dataStatus'
import { COLLECT_REPORT_BADGE } from '@/utils/labels'

/** S7 수집기 표: 키 상태 + 마지막(또는 진행 중인) 수집의 결과 */
const props = defineProps<{ collectors: CollectorStatus[]; collect: CollectState }>()

const GRID = 'grid-cols-[132px_minmax(0,1.5fr)_156px_100px_minmax(0,1fr)]'

const reportByName = computed(() => new Map(props.collect.reports.map((r) => [r.collector, r])))

/** 보고서 한 줄 표기: ok는 건수 요약, 그 외는 메시지 */
function detail(r: CollectReport): string {
  if (r.status === 'ok') return summarizeCounts(r.counts) || r.message
  return r.message
}
</script>

<template>
  <section class="rp-card overflow-hidden" role="table" aria-label="수집기">
    <div class="flex items-baseline gap-3 px-5 py-3">
      <h2 class="m-0 text-body font-bold">수집기</h2>
      <span class="text-caption text-ink-3">API 키는 서버 환경 변수(.env)로 설정합니다</span>
    </div>

    <div v-if="collectors.length === 0" class="px-5 pb-5">
      <EmptyState compact title="등록된 수집기가 없습니다" />
    </div>

    <template v-else>
      <div class="rp-thead grid gap-4 px-5 py-2.5" :class="GRID" role="row">
        <span role="columnheader">수집기</span>
        <span role="columnheader">설명</span>
        <span role="columnheader">필요한 키</span>
        <span role="columnheader">키 상태</span>
        <span role="columnheader">최근 결과</span>
      </div>
      <div
        v-for="c in collectors"
        :key="c.name"
        class="grid items-center gap-4 border-t border-line-subtle px-5 py-2.5 text-small"
        :class="GRID"
        role="row"
      >
        <span class="font-mono text-[12px] font-semibold">{{ c.name }}</span>
        <span class="ellipsis text-ink-2" :title="c.description">{{ c.description }}</span>
        <span class="ellipsis font-mono text-[12px]" :class="c.required_key ? 'text-ink-2' : 'text-ink-4'" :title="c.required_key ?? undefined">
          {{ c.required_key ?? '불필요' }}
        </span>
        <span>
          <RpBadge v-if="c.key_present" variant="pass">✓ 설정됨</RpBadge>
          <RpBadge v-else variant="warn" :tooltip="`${c.required_key} 환경 변수가 없어 이 수집기는 건너뜁니다`">⚠ 키 없음</RpBadge>
        </span>
        <span class="flex min-w-0 items-center gap-2">
          <template v-if="reportByName.get(c.name)">
            <RpBadge :variant="COLLECT_REPORT_BADGE[reportByName.get(c.name)!.status].variant">
              {{ COLLECT_REPORT_BADGE[reportByName.get(c.name)!.status].text }}
            </RpBadge>
            <span
              class="ellipsis min-w-0"
              :class="reportByName.get(c.name)!.status === 'error' ? 'text-fail' : 'text-ink-2'"
              :title="reportByName.get(c.name)!.message"
            >
              {{ detail(reportByName.get(c.name)!) }}
            </span>
          </template>
          <template v-else-if="collect.running">
            <RpSpinner />
            <span class="text-caption font-semibold text-navy-900">대기/실행 중</span>
          </template>
          <span v-else class="text-ink-4">—</span>
        </span>
      </div>
    </template>
  </section>
</template>
