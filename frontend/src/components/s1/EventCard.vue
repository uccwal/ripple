<script setup lang="ts">
import type { EventSummary } from '@/api/types'
import CalcNum from '@/components/common/CalcNum.vue'
import CountryCode from '@/components/common/CountryCode.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import RpButton from '@/components/common/RpButton.vue'
import { formatDate } from '@/utils/format'
import { formatPct } from '@/utils/format'
import { ACTUAL_TIP, AUTO_RUN_TIP, RELEVANCE_BADGE, RELEVANCE_TIP } from '@/utils/labels'

defineProps<{ event: EventSummary }>()
</script>

<template>
  <article class="rp-card flex flex-col gap-3 px-5 py-[18px]">
    <div class="flex items-center gap-2">
      <CountryCode :code="event.country" />
      <span class="text-small text-ink-2">{{ event.country_name }}</span>
      <RpBadge variant="outline">{{ event.type_name }}</RpBadge>
      <RpBadge v-if="event.relevance" :variant="RELEVANCE_BADGE[event.relevance].variant" :tooltip="RELEVANCE_TIP">
        {{ RELEVANCE_BADGE[event.relevance].text }}
      </RpBadge>
      <RpBadge
        v-if="event.is_demo"
        variant="virtual"
        tooltip="시연용 예시 이벤트입니다. 실제 수집된 발표가 아닙니다."
        >예시</RpBadge
      >
      <span class="tnum ml-auto text-caption font-normal text-ink-3">{{ formatDate(event.announced_at) }}</span>
    </div>

    <div>
      <h3 class="m-0 text-heading font-bold tracking-[-0.01em]">{{ event.title }}</h3>
      <div v-if="event.title_orig" class="ellipsis mt-0.5 text-micro text-ink-3" :title="event.title_orig" lang="en">{{ event.title_orig }}</div>
      <p class="m-0 mt-0.5 text-small text-ink-2">{{ event.summary }}</p>
    </div>

    <div v-if="event.value_text || event.last_run?.portfolio_pnl != null" class="grid gap-2" :class="event.value_text && event.last_run?.portfolio_pnl != null ? 'grid-cols-2' : 'grid-cols-1'">
      <div v-if="event.value_text" class="flex items-center justify-between rounded bg-bg px-3.5 py-2.5">
        <span class="text-caption font-normal text-ink-3">핵심 수치</span>
        <span class="tnum text-xl font-bold text-navy-900">{{ event.value_text }}</span>
      </div>
      <div v-if="event.last_run?.portfolio_pnl != null" class="flex items-center justify-between rounded bg-bg px-3.5 py-2.5">
        <span class="flex flex-col text-caption font-normal text-ink-3">
          <span>예상 손익 <span v-if="event.last_run.auto" class="text-navy-700" :title="AUTO_RUN_TIP">· 자동</span></span>
          <span v-if="event.last_run.actual_pnl != null" class="tnum text-micro" :title="ACTUAL_TIP">
            실제 {{ formatPct(event.last_run.actual_pnl) }}
            <span v-if="event.last_run.direction_hit != null" :class="event.last_run.direction_hit ? 'text-pass' : 'text-warn'">{{ event.last_run.direction_hit ? '방향 적중' : '방향 불일치' }}</span>
          </span>
        </span>
        <CalcNum class="text-xl font-bold" :value="event.last_run.portfolio_pnl" :to="{ name: 'run', params: { id: event.last_run.run_id } }" label="예상 손익" />
      </div>
    </div>

    <div class="flex items-center gap-2">
      <span class="text-caption font-normal text-ink-3">
        출처
        <a v-if="event.source_url" :href="event.source_url" target="_blank" rel="noopener noreferrer" class="text-ink-3 no-underline hover:underline">{{ event.source }}</a>
        <template v-else>{{ event.source }}</template>
      </span>
      <RpBadge v-if="event.last_run?.validation_status === 'pass'" variant="pass" tooltip="Validator 규칙 통과">✓ 검증</RpBadge>
      <RpBadge v-else-if="event.last_run?.validation_status === 'warn'" variant="warn" tooltip="경고가 있는 분석 결과">⚠ 경고</RpBadge>
      <template v-if="event.last_run">
        <RouterLink
          class="ml-auto text-caption font-semibold text-navy-900 no-underline hover:underline"
          :to="{ name: 'new', query: { event: event.event_id } }"
          title="다른 포트폴리오·기간으로 새 분석"
          >다시 분석</RouterLink
        >
        <RpButton variant="outline" size="sm" :to="{ name: 'run', params: { id: event.last_run.run_id } }">결과 보기</RpButton>
      </template>
      <RpButton v-else class="ml-auto" variant="outline" size="sm" :to="{ name: 'new', query: { event: event.event_id } }">분석하기</RpButton>
    </div>
  </article>
</template>
