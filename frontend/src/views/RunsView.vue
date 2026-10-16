<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import type { RunListItem } from '@/api/types'
import CalcNum from '@/components/common/CalcNum.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import RpButton from '@/components/common/RpButton.vue'
import RpSpinner from '@/components/common/RpSpinner.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import { isActiveStatus } from '@/stores/liveRuns'
import { useHistoryStore } from '@/stores/history'
import { formatDateTime } from '@/utils/format'
import { ENTRY_SHORT, VALIDATION_BADGE } from '@/utils/labels'

/** S6 실행 이력 (/runs) */
const router = useRouter()
const history = useHistoryStore()
const { runs, state, error } = storeToRefs(history)

const GRID = 'grid-cols-[150px_124px_minmax(0,1fr)_230px_100px_110px_80px]'

function badgeFor(r: RunListItem) {
  if (r.status === 'failed') return VALIDATION_BADGE.fail
  return r.validation_status ? VALIDATION_BADGE[r.validation_status] : null
}

function open(id: string): void {
  void router.push({ name: 'run', params: { id } })
}

onMounted(() => void history.load())
</script>

<template>
  <div class="mx-auto flex max-w-[1440px] flex-col gap-4 px-8 pb-12 pt-7">
    <div>
      <h1 class="m-0 text-title font-bold tracking-[-0.02em]">실행 이력</h1>
      <div class="text-small text-ink-3">모든 실행은 calc_log와 Agent 단계 기록을 함께 보관합니다.</div>
    </div>

    <ErrorState v-if="state === 'error'" title="실행 이력을 불러오지 못했습니다" :message="error" @retry="history.load()" />

    <EmptyState v-else-if="state === 'ready' && runs.length === 0" title="분석 기록이 없습니다" description="정책 이벤트나 시나리오로 첫 분석을 시작하세요.">
      <RpButton :to="{ name: 'new' }">새 분석</RpButton>
    </EmptyState>

    <div v-else class="rp-card overflow-hidden" role="table" aria-label="실행 이력">
      <div class="rp-thead grid gap-4 px-5 py-2.5" :class="GRID" role="row">
        <span role="columnheader">실행일시</span>
        <span role="columnheader">입구 유형</span>
        <span role="columnheader">이벤트·시나리오 요약</span>
        <span role="columnheader">포트폴리오</span>
        <span role="columnheader" class="text-right">예상 손익</span>
        <span role="columnheader">검증 상태</span>
        <span />
      </div>

      <template v-if="state !== 'ready'">
        <div v-for="i in 6" :key="i" class="grid items-center gap-4 border-t border-line-subtle px-5 py-3" :class="GRID" aria-hidden="true">
          <SkeletonBar w="110px" :h="12" />
          <SkeletonBar w="52px" :h="22" :radius="4" />
          <SkeletonBar w="70%" :h="12" tone="strong" />
          <SkeletonBar w="160px" :h="12" />
          <SkeletonBar class="justify-self-end" w="48px" :h="12" />
          <SkeletonBar w="56px" :h="22" :radius="4" />
          <SkeletonBar w="52px" :h="30" :radius="6" />
        </div>
      </template>

      <div v-for="r in runs" v-else :key="r.run_id" class="grid items-center gap-4 border-t border-line-subtle px-5 py-3 text-small" :class="GRID" role="row">
        <span class="tnum text-ink-2">{{ formatDateTime(r.created_at) }}</span>
        <span class="flex gap-1"><RpBadge variant="entry">{{ ENTRY_SHORT[r.entry] }}</RpBadge><RpBadge v-if="r.auto" variant="virtual" tooltip="수집 직후 자동 사전분석">자동</RpBadge></span>
        <span class="ellipsis font-semibold" :title="r.title">{{ r.title }}</span>
        <span class="ellipsis text-ink-2">{{ r.portfolio_name }}</span>
        <CalcNum
          class="justify-self-end font-bold"
          :value="r.status === 'failed' ? null : r.portfolio_pnl"
          :to="{ name: 'run', params: { id: r.run_id } }"
          label="예상 손익"
        />
        <span>
          <span v-if="isActiveStatus(r.status)" class="inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-sm bg-navy-50 px-2 text-caption font-semibold text-navy-900">
            <RpSpinner :size="10" />실행 중
          </span>
          <RpBadge v-else-if="badgeFor(r)" :variant="badgeFor(r)!.variant">{{ badgeFor(r)!.text }}</RpBadge>
          <span v-else class="text-ink-4">—</span>
        </span>
        <button
          type="button"
          class="h-[30px] flex-none cursor-pointer whitespace-nowrap rounded border border-line-strong bg-white px-3 text-caption font-semibold text-ink hover:border-navy-900 hover:text-navy-900"
          @click="open(r.run_id)"
        >
          열기
        </button>
      </div>
    </div>
  </div>
</template>
