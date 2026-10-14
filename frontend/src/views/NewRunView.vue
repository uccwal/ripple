<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { api, errorMessage } from '@/api/client'
import type { Entry } from '@/api/types'
import CountryCode from '@/components/common/CountryCode.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import RpButton from '@/components/common/RpButton.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import { useEventStore } from '@/stores/events'
import { useLiveRunsStore } from '@/stores/liveRuns'
import { usePortfolioStore } from '@/stores/portfolios'
import { formatDate } from '@/utils/format'
import { PIPELINE } from '@/utils/labels'

/** S2 새 분석 (/new?event=<id> | ?entry=scenario) */
const route = useRoute()
const router = useRouter()
const eventStore = useEventStore()
const portfolioStore = usePortfolioStore()
const live = useLiveRunsStore()
const { allEvents, allState, allError } = storeToRefs(eventStore)
const { list: portfolios, listState, listError } = storeToRefs(portfolioStore)

const EXAMPLES = ['유가 30% 급등 + 원화 10% 약세', '미국 금리 1%p 인상', '반도체 업종 20% 하락']
const HORIZON_MIN = 1
const HORIZON_MAX = 250

const entry = ref<Entry>(route.query.entry === 'scenario' ? 'scenario' : 'event')
const eventId = ref<string>(typeof route.query.event === 'string' ? route.query.event : '')
const scenarioText = ref('')
const portfolioId = ref<string>('')
const horizon = ref('20')
const submitting = ref(false)
const submitError = ref<string | null>(null)

const selectedEvent = computed(() => allEvents.value.find((e) => e.event_id === eventId.value) ?? null)
const horizonNum = computed(() => Number(horizon.value))
const horizonValid = computed(
  () => Number.isInteger(horizonNum.value) && horizonNum.value >= HORIZON_MIN && horizonNum.value <= HORIZON_MAX,
)

const blocker = computed<string | null>(() => {
  if (entry.value === 'event' && !selectedEvent.value) return '분석할 정책 이벤트를 선택하세요.'
  if (entry.value === 'scenario' && scenarioText.value.trim().length === 0) return '시나리오를 입력하세요.'
  if (!portfolioId.value) return '포트폴리오를 선택하세요.'
  if (!horizonValid.value) return `분석 기간은 ${HORIZON_MIN}~${HORIZON_MAX}영업일이어야 합니다.`
  return null
})

function entryCardClass(e: Entry): string {
  // 선택 시 테두리 2px → 패딩을 1px 줄여 내용이 움직이지 않게 한다.
  return entry.value === e ? 'border-2 border-navy-900 bg-surface-selected p-[19px]' : 'border border-line bg-surface p-5'
}

function onHorizon(ev: Event): void {
  horizon.value = (ev.target as HTMLInputElement).value.replace(/[^0-9]/g, '')
}

async function start(): Promise<void> {
  if (blocker.value || submitting.value) return
  submitting.value = true
  submitError.value = null
  try {
    const res = await api.createRun({
      entry: entry.value,
      portfolio_id: portfolioId.value,
      horizon_days: horizonNum.value,
      ...(entry.value === 'event' ? { event_id: eventId.value } : { scenario_text: scenarioText.value.trim() }),
    })
    void live.trackById(res.run_id)
    await router.push({ name: 'run', params: { id: res.run_id } })
  } catch (err) {
    submitError.value = errorMessage(err)
  } finally {
    submitting.value = false
  }
}

watch(allEvents, (list) => {
  if (!list.some((e) => e.event_id === eventId.value)) eventId.value = list[0]?.event_id ?? ''
})
watch(
  () => portfolioStore.selectedId,
  (id) => {
    if (!portfolioId.value && id) portfolioId.value = id
  },
  { immediate: true },
)
// 같은 화면에서 쿼리만 바뀌는 경우 (상단 바 "새 분석" 등)
watch(
  () => route.query,
  (q) => {
    if (q.entry === 'scenario') entry.value = 'scenario'
    if (typeof q.event === 'string') {
      entry.value = 'event'
      eventId.value = q.event
    }
  },
)

onMounted(() => {
  void eventStore.fetchAll()
  if (portfolioStore.listState !== 'ready') void portfolioStore.loadList()
})
</script>

<template>
  <div class="mx-auto flex max-w-[920px] flex-col gap-5 px-8 pb-16 pt-8">
    <div>
      <h1 class="m-0 text-title font-bold tracking-[-0.02em]">새 분석</h1>
      <div class="text-small text-ink-3">분석 입구와 대상 포트폴리오를 정합니다.</div>
    </div>

    <div class="rp-section-label">1. 분석 입구</div>
    <div class="grid grid-cols-2 gap-4" role="radiogroup" aria-label="분석 입구">
      <button
        v-for="opt in [
          { key: 'event' as const, title: '정책 이벤트로 시작', desc: '수집된 정책 발표를 구조화하고 파급 경로부터 추론합니다. 7단계.' },
          { key: 'scenario' as const, title: '시나리오 직접 입력', desc: '자연어로 충격을 입력하면 변수와 충격값으로 변환합니다. 5단계.' },
        ]"
        :key="opt.key"
        type="button"
        role="radio"
        :aria-checked="entry === opt.key"
        class="flex cursor-pointer gap-3 rounded-card text-left"
        :class="entryCardClass(opt.key)"
        @click="entry = opt.key"
      >
        <span
          class="mt-0.5 h-[18px] w-[18px] flex-none rounded-full"
          :class="entry === opt.key ? 'border-[5px] border-navy-900' : 'border-[1.5px] border-line-strong'"
          aria-hidden="true"
        />
        <span>
          <span class="block text-heading font-bold text-ink">{{ opt.title }}</span>
          <span class="mt-1 block text-small text-ink-2">{{ opt.desc }}</span>
        </span>
      </button>
    </div>

    <!-- 이벤트 입구 -->
    <div v-if="entry === 'event'" class="rp-card flex flex-col gap-3 px-5 py-[18px]">
      <ErrorState v-if="allState === 'error'" title="정책 이벤트를 불러오지 못했습니다" :message="allError" @retry="eventStore.fetchAll()" />
      <template v-else-if="allState === 'ready' && allEvents.length === 0">
        <div class="text-small text-ink-2">
          수집된 정책 이벤트가 없습니다. 시나리오를 직접 입력해 분석할 수 있습니다.
          <button type="button" class="cursor-pointer border-0 bg-transparent p-0 font-semibold text-navy-900" @click="entry = 'scenario'">
            시나리오 입력으로 전환
          </button>
        </div>
      </template>
      <template v-else-if="allState === 'ready'">
        <label class="flex items-center gap-3">
          <span class="text-caption font-normal text-ink-3">선택된 이벤트</span>
          <select v-model="eventId" class="rp-select ml-auto h-8 min-w-[320px] text-small">
            <option v-for="e in allEvents" :key="e.event_id" :value="e.event_id">{{ e.country_name }} · {{ e.title }}</option>
          </select>
        </label>
        <div v-if="selectedEvent" class="flex items-center gap-4 rounded bg-bg px-4 py-3.5">
          <CountryCode :code="selectedEvent.country" tone="white" />
          <div class="min-w-0 flex-1">
            <div class="text-[15px] font-bold">{{ selectedEvent.title }}</div>
            <div class="tnum text-caption font-normal text-ink-3">
              {{ selectedEvent.country_name }} · {{ selectedEvent.type_name }} · {{ formatDate(selectedEvent.announced_at) }} · {{ selectedEvent.source }}
            </div>
          </div>
          <span class="tnum whitespace-nowrap text-lg font-bold text-navy-900">{{ selectedEvent.value_text }}</span>
        </div>
      </template>
      <template v-else>
        <div class="flex items-center gap-3"><SkeletonBar w="80px" :h="12" /><SkeletonBar class="ml-auto" w="320px" :h="32" :radius="6" /></div>
        <SkeletonBar :h="64" tone="block" :radius="6" />
      </template>
    </div>

    <!-- 시나리오 입구 -->
    <div v-else class="rp-card flex flex-col gap-3 px-5 py-[18px]">
      <textarea
        v-model="scenarioText"
        class="rp-input min-h-24 w-full resize-y p-3 text-body"
        placeholder="예: 유가 30% 급등과 원화 10% 약세가 동시에 발생"
        aria-label="시나리오"
      />
      <div class="flex flex-wrap gap-2">
        <button
          v-for="ex in EXAMPLES"
          :key="ex"
          type="button"
          class="flex h-7 flex-none cursor-pointer items-center whitespace-nowrap rounded-[14px] border border-line bg-bg px-3 text-small text-ink-2 hover:border-navy-900 hover:text-navy-900"
          @click="scenarioText = ex"
        >
          {{ ex }}
        </button>
      </div>
    </div>

    <div class="rp-section-label mt-2">2. 대상과 기간</div>
    <div class="rp-card grid grid-cols-[minmax(0,1fr)_220px] gap-5 px-5 py-[18px]">
      <div class="flex flex-col gap-1.5">
        <span class="text-caption font-normal text-ink-3">포트폴리오</span>
        <div v-if="listState === 'error'" class="flex items-center gap-3 text-small text-fail">
          {{ listError }}
          <RpButton variant="secondary" size="sm" @click="portfolioStore.loadList()">다시 시도</RpButton>
        </div>
        <SkeletonBar v-else-if="listState !== 'ready'" :h="38" :radius="6" />
        <div v-else class="flex items-center gap-2.5">
          <select v-model="portfolioId" class="rp-select h-[38px] flex-1 px-2.5 text-body" aria-label="포트폴리오">
            <option v-for="p in portfolios" :key="p.portfolio_id" :value="p.portfolio_id">{{ p.name }}</option>
          </select>
          <RpBadge variant="virtual">가상 포트폴리오</RpBadge>
        </div>
      </div>
      <div class="flex flex-col gap-1.5">
        <span class="text-caption font-normal text-ink-3">분석 기간</span>
        <div class="flex items-center gap-2">
          <input
            :value="horizon"
            inputmode="numeric"
            class="rp-input tnum h-[38px] w-[90px] text-right text-body"
            :class="{ '!border-fail': !horizonValid }"
            aria-label="분석 기간 (영업일)"
            @input="onHorizon"
          />
          <span class="text-small text-ink-2">영업일</span>
        </div>
      </div>
    </div>

    <div class="mt-2 flex items-center gap-4">
      <div class="flex min-w-0 flex-col gap-0.5">
        <div class="text-caption font-normal text-ink-3">{{ PIPELINE[entry] }}</div>
        <div v-if="submitError" class="text-caption font-semibold text-fail" role="alert">{{ submitError }}</div>
        <div v-else-if="blocker && (allState === 'ready' || entry === 'scenario')" class="text-caption font-normal text-ink-3">{{ blocker }}</div>
      </div>
      <RpButton class="ml-auto" size="lg" :disabled="!!blocker || submitting" @click="start">
        {{ submitting ? '시작하는 중…' : '분석 시작' }}
      </RpButton>
    </div>
  </div>
</template>
