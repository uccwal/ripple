<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { api, errorMessage, reportUrl } from '@/api/client'
import ErrorState from '@/components/common/ErrorState.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import RpButton from '@/components/common/RpButton.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import PathTab from '@/components/s3/PathTab.vue'
import ReportTab from '@/components/s3/ReportTab.vue'
import ResultTab from '@/components/s3/ResultTab.vue'
import RunFailedCard from '@/components/s3/RunFailedCard.vue'
import RunningPlaceholder from '@/components/s3/RunningPlaceholder.vue'
import RunSummaryBar from '@/components/s3/RunSummaryBar.vue'
import RunTabs from '@/components/s3/RunTabs.vue'
import RunTimeline from '@/components/s3/RunTimeline.vue'
import ScenarioTab from '@/components/s3/ScenarioTab.vue'
import { useLiveRunsStore } from '@/stores/liveRuns'
import { useMetaStore } from '@/stores/meta'
import { isRunTab, useRunStore } from '@/stores/run'
import { useUiStore } from '@/stores/ui'
import { ENTRY_LABEL } from '@/utils/labels'

/** S3 분석 워크스페이스 (/runs/:id[?tab=result]) */
const route = useRoute()
const router = useRouter()
const store = useRunStore()
const live = useLiveRunsStore()
const ui = useUiStore()
const { meta } = storeToRefs(useMetaStore())
const {
  run,
  state,
  error,
  activeTab,
  selectedNodeId,
  expandedStep,
  status,
  isActive,
  steps,
  retryLoops,
  elapsedMs,
  currentText,
  draftRows,
  isDirty,
  hasInvalid,
  canRecalc,
  recalcPending,
  recalcError,
} = storeToRefs(store)

const routeId = computed(() => String(route.params.id ?? ''))

watch(
  routeId,
  (id) => {
    if (!id) return
    const tab = route.query.tab
    void store.load(id, isRunTab(tab) ? tab : undefined)
  },
  { immediate: true },
)

/** 좌측 패널 하단 문구: offline 모드면 LLM 없이 규칙으로 실행되었음을 밝힌다. */
const modelNote = computed(() => {
  const mode = run.value?.llm_mode ?? meta.value?.llm_mode
  const model = mode === 'offline' ? 'offline 규칙' : meta.value?.model_default ?? 'claude-haiku-5-5'
  return `모델 ${model} · 계산은 engine 모듈에서만 수행`
})
const modelTip = computed(() =>
  (run.value?.llm_mode ?? meta.value?.llm_mode) === 'offline'
    ? 'API 키 없이 실행되어 LLM 대신 규칙 기반 Agent가 사용되었습니다. 수치는 어느 모드에서나 engine 모듈이 계산합니다.'
    : undefined,
)

const subtitle = computed(() => (run.value ? `${run.value.portfolio.name} · ${run.value.horizon_days}영업일` : ''))
const isFailed = computed(() => status.value === 'failed')

/* ---------- 액션 ---------- */

const restartPending = ref(false)

/** 같은 입력으로 새 실행 (다시 시도 · 다시 실행) */
async function restart(): Promise<void> {
  const r = run.value
  if (!r || restartPending.value) return
  restartPending.value = true
  try {
    const res = await api.createRun({
      entry: r.entry,
      portfolio_id: r.portfolio.portfolio_id,
      horizon_days: r.horizon_days,
      ...(r.entry === 'event' ? { event_id: r.event?.event_id } : { scenario_text: r.input_text ?? r.title }),
    })
    void live.trackById(res.run_id)
    await router.push({ name: 'run', params: { id: res.run_id } })
  } catch (err) {
    ui.showToast(`다시 실행하지 못했습니다 · ${errorMessage(err)}`)
  } finally {
    restartPending.value = false
  }
}

function downloadReport(): void {
  if (!run.value) return
  const a = document.createElement('a')
  a.href = reportUrl(run.value.run_id, 'md')
  a.download = `${run.value.run_id}.md`
  document.body.appendChild(a)
  a.click()
  a.remove()
}

async function recalc(): Promise<void> {
  const id = await store.submitRecalc()
  if (id) await router.push({ name: 'run', params: { id }, query: { tab: 'result' } })
}
</script>

<template>
  <div class="flex min-h-[calc(100vh-56px)]">
    <!-- 좌측 실행 과정 패널 -->
    <aside class="w-run-panel flex-none border-r border-line bg-surface" aria-label="실행 과정">
      <div class="sticky top-14 h-[calc(100vh-56px)] overflow-y-auto">
        <RunTimeline
          v-if="run"
          :run-id="run.run_id"
          :steps="steps"
          :retry-loops="retryLoops"
          :elapsed-ms="elapsedMs"
          :active="isActive"
          :expanded="expandedStep"
          :model-note="modelNote"
          :model-tip="modelTip"
          @toggle="store.toggleStep"
        />
        <div v-else class="flex flex-col gap-3 px-4 py-[18px]" aria-hidden="true">
          <div class="flex justify-between"><SkeletonBar w="64px" :h="14" tone="strong" /><SkeletonBar w="36px" :h="12" /></div>
          <SkeletonBar w="140px" :h="10" />
          <div v-for="i in 7" :key="i" class="flex gap-3 py-2.5">
            <SkeletonBar w="24px" :h="24" :radius="12" />
            <div class="flex flex-1 flex-col gap-1.5"><SkeletonBar w="70%" :h="12" tone="strong" /><SkeletonBar w="50%" :h="10" /></div>
          </div>
        </div>
      </div>
    </aside>

    <!-- 메인 -->
    <div class="flex min-w-0 flex-1 flex-col gap-4 px-6 pb-12 pt-5">
      <ErrorState v-if="state === 'error' && !run" title="실행을 불러오지 못했습니다" :message="error" @retry="store.load(routeId)">
        <RpButton variant="secondary" :to="{ name: 'runs' }">실행 이력으로</RpButton>
      </ErrorState>

      <template v-else-if="!run">
        <div class="flex items-center gap-2.5" aria-hidden="true">
          <SkeletonBar w="72px" :h="22" :radius="4" />
          <SkeletonBar w="320px" :h="18" tone="strong" />
        </div>
        <RunningPlaceholder current="실행 정보를 불러오는 중" />
      </template>

      <template v-else>
        <div class="flex items-center gap-2.5">
          <RpBadge variant="entry">{{ ENTRY_LABEL[run.entry] }}</RpBadge>
          <h1 class="m-0 min-w-0 text-lg font-bold tracking-[-0.01em]">{{ run.title }}</h1>
          <span class="whitespace-nowrap text-small text-ink-3">{{ subtitle }}</span>
          <RpBadge
            v-if="run.parent_run_id"
            variant="outline"
            class="ml-auto"
            :tooltip="`시나리오를 고쳐 다시 계산한 실행입니다. 원래 실행: ${run.parent_run_id}`"
          >
            재계산 · <RouterLink :to="{ name: 'run', params: { id: run.parent_run_id } }" class="font-mono text-[11px]">{{ run.parent_run_id }}</RouterLink>
          </RpBadge>
        </div>

        <RunningPlaceholder v-if="isActive" :current="currentText" />

        <RunFailedCard v-else-if="isFailed" :reason="run.error" :retry-pending="restartPending" @retry="restart" />

        <template v-else>
          <RunSummaryBar :run="run" :rerun-pending="restartPending" @download="downloadReport" @rerun="restart" />

          <div
            v-if="status === 'partial'"
            class="rounded border border-warn-loop/40 bg-warn-note px-4 py-2.5 text-small text-warn"
            role="status"
          >
            일부 단계가 완료되지 않아 결과가 부분적입니다. 실행 과정의 단계 메모를 확인하세요.
          </div>

          <RunTabs :active="activeTab" :scenario-dirty="isDirty" @select="store.setTab" />

          <PathTab
            v-if="activeTab === 'path'"
            :run="run"
            :selected-node-id="selectedNodeId"
            @select="store.selectNode"
            @go-scenario="store.setTab('scen')"
          />
          <ScenarioTab
            v-else-if="activeTab === 'scen'"
            :run="run"
            :rows="draftRows"
            :dirty="isDirty"
            :invalid="hasInvalid"
            :can-recalc="canRecalc"
            :pending="recalcPending"
            :error="recalcError"
            @edit="store.setDraft"
            @reset="store.resetDraft"
            @recalc="recalc"
          />
          <ResultTab v-else-if="activeTab === 'result'" :run="run" />
          <ReportTab v-else :run="run" />
        </template>
      </template>
    </div>
  </div>
</template>
