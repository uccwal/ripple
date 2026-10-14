<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useLiveRunsStore } from '@/stores/liveRuns'
import { useMetaStore } from '@/stores/meta'
import { formatElapsed } from '@/utils/format'
import LogoMark from './LogoMark.vue'
import RpBadge from './RpBadge.vue'
import RpButton from './RpButton.vue'
import RpSpinner from './RpSpinner.vue'

const route = useRoute()
const router = useRouter()
const live = useLiveRunsStore()
const { meta } = storeToRefs(useMetaStore())

const NAV = [
  { name: 'events', label: '이벤트', to: '/' },
  { name: 'portfolios', label: '포트폴리오', to: '/portfolios' },
  { name: 'runs', label: '실행 이력', to: '/runs' },
] as const

const SYNTHETIC_TIP =
  '시계열 일부가 데모용 합성 데이터입니다. 수집기(FRED·ECOS·시세 등)가 API 키로 실행되기 전까지 합성 시리즈로 계산합니다. 실제 시장 데이터가 아닙니다.'

const runningPill = computed(() => {
  const r = live.primary
  if (!r) return null
  return { runId: r.runId, elapsed: formatElapsed(live.elapsedOf(r.runId)) }
})

function openRunning(): void {
  if (runningPill.value) void router.push({ name: 'run', params: { id: runningPill.value.runId } })
}
</script>

<template>
  <header class="sticky top-0 z-30 flex h-14 items-center gap-9 border-b border-line bg-surface px-6">
    <RouterLink to="/" class="flex items-center gap-2.5 no-underline" aria-label="RIPPLE 홈">
      <LogoMark />
      <span class="text-base font-extrabold tracking-[0.12em] text-navy-900">RIPPLE</span>
    </RouterLink>

    <nav class="flex h-14 gap-1" aria-label="주 메뉴">
      <RouterLink
        v-for="n in NAV"
        :key="n.name"
        :to="n.to"
        class="flex items-center whitespace-nowrap border-b-2 px-3.5 text-body font-semibold no-underline"
        :class="route.name === n.name ? 'border-navy-900 text-navy-900' : 'border-transparent text-ink-2 hover:text-navy-900'"
        :aria-current="route.name === n.name ? 'page' : undefined"
      >
        {{ n.label }}
      </RouterLink>
    </nav>

    <div class="flex-1" />

    <div class="flex items-center gap-9">
      <RpBadge v-if="meta?.synthetic_data" variant="warn" :tooltip="SYNTHETIC_TIP">⚠ 합성 데이터</RpBadge>

      <button
        v-if="runningPill"
        type="button"
        class="flex h-[30px] cursor-pointer items-center gap-2 rounded-[15px] border-0 bg-navy-50 px-3 text-caption font-semibold text-navy-900"
        @click="openRunning"
      >
        <RpSpinner />
        <span class="tnum whitespace-nowrap">분석 실행 중 · {{ runningPill.elapsed }}</span>
      </button>

      <RouterLink
        to="/system"
        class="whitespace-nowrap text-small font-semibold no-underline"
        :class="route.name === 'system' ? 'text-navy-900' : 'text-ink-3 hover:text-navy-900'"
      >
        컴포넌트·토큰
      </RouterLink>

      <RpButton :to="{ name: 'new' }">＋ 새 분석</RpButton>
    </div>
  </header>
</template>
