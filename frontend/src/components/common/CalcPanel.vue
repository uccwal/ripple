<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import type { CalcCell, CalcEntry } from '@/api/types'
import { useCalcLogStore } from '@/stores/calcLog'
import { useUiStore } from '@/stores/ui'
import { formatDate, pnlColor } from '@/utils/format'
import RpBadge from './RpBadge.vue'
import RpButton from './RpButton.vue'
import SkeletonBar from './SkeletonBar.vue'

/**
 * S5 계산 근거 패널 (전역 슬라이드 오버)
 * uiStore.calcPanel {runId, key} → GET /api/runs/{id}/calc-log (실행별 캐시) → entries[key]
 */
const ui = useUiStore()
const calcLogs = useCalcLogStore()
const { calcPanel } = storeToRefs(ui)

const closeBtn = ref<HTMLButtonElement | null>(null)
let returnFocus: HTMLElement | null = null

const cache = computed(() => (calcPanel.value ? calcLogs.entry(calcPanel.value.runId) : null))
const log = computed(() => cache.value?.data ?? null)
const entry = computed<CalcEntry | null>(() => (calcPanel.value && log.value ? log.value.entries[calcPanel.value.key] ?? null : null))

const valueColor = computed(() => (entry.value && entry.value.value !== null ? pnlColor(entry.value.value) : '#141A24'))

/** 열 폭: 각 열의 최대 글자 수에 비례 (첫 열은 이름이므로 가중) */
const gridTemplate = computed(() => {
  const e = entry.value
  if (!e) return ''
  return e.columns
    .map((h, i) => {
      const longest = Math.max(h.length, ...e.rows.map((r) => r[i]?.v.length ?? 0))
      const weight = Math.min(Math.max(longest, 4), 18) * (i === 0 ? 1.15 : 1)
      return `minmax(0,${weight.toFixed(2)}fr)`
    })
    .join(' ')
})

function cellStyle(cell: CalcCell | undefined, i: number) {
  const hasNum = typeof cell?.num === 'number'
  return {
    textAlign: i === 0 ? ('left' as const) : ('right' as const),
    color: hasNum ? pnlColor(cell!.num) : '#141A24',
    fontWeight: hasNum ? 700 : i === 0 ? 600 : 400,
  }
}

const hashShort = computed(() => {
  const h = log.value?.code_hash ?? ''
  return h.replace(/^sha256:/, '').slice(0, 7)
})

function close(): void {
  ui.closeCalc()
}

function onKey(ev: KeyboardEvent): void {
  if (ev.key === 'Escape' && calcPanel.value) close()
}

watch(
  calcPanel,
  async (target, prev) => {
    if (target) {
      if (!prev) returnFocus = document.activeElement as HTMLElement | null
      void calcLogs.load(target.runId)
      await nextTick()
      closeBtn.value?.focus()
    } else if (prev) {
      returnFocus?.focus?.()
      returnFocus = null
    }
  },
  { immediate: true },
)

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div v-if="calcPanel" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-scrim" aria-hidden="true" @click="close" />
      <aside
        class="absolute bottom-0 right-0 top-0 flex w-calc-panel flex-col gap-[18px] overflow-auto bg-surface px-6 pb-8 pt-5 shadow-panel"
        role="dialog"
        aria-modal="true"
        aria-label="계산 근거"
      >
        <div class="flex items-center">
          <span class="text-caption font-bold tracking-[0.04em] text-ink-3">계산 근거</span>
          <button
            ref="closeBtn"
            type="button"
            class="ml-auto flex h-7 w-7 cursor-pointer items-center justify-center rounded border-0 bg-transparent text-lg text-ink-2 hover:bg-bg"
            aria-label="닫기"
            @click="close"
          >
            ×
          </button>
        </div>

        <!-- 로딩 -->
        <template v-if="cache?.state === 'loading' || cache?.state === 'idle'">
          <div class="flex flex-col gap-2">
            <SkeletonBar w="120px" :h="12" />
            <SkeletonBar w="180px" :h="36" tone="strong" :radius="4" />
            <SkeletonBar w="220px" :h="12" />
          </div>
          <SkeletonBar :h="72" tone="block" :radius="6" />
          <div class="flex flex-col gap-2">
            <SkeletonBar v-for="i in 5" :key="i" :h="12" />
          </div>
        </template>

        <!-- 오류 -->
        <div v-else-if="cache?.state === 'error'" class="flex flex-col items-start gap-3" role="alert">
          <div class="text-[15px] font-bold">계산 근거를 불러오지 못했습니다</div>
          <div class="text-small text-ink-2">{{ cache.error }}</div>
          <RpButton @click="calcLogs.load(calcPanel.runId, true)">다시 시도</RpButton>
        </div>

        <!-- 키 없음 -->
        <div v-else-if="!entry" class="flex flex-col gap-2">
          <div class="text-[15px] font-bold">이 수치의 계산 근거가 없습니다</div>
          <div class="text-small text-ink-3">
            calc_log에 <code class="font-mono text-[12px]">{{ calcPanel.key }}</code> 항목이 기록되지 않았습니다.
          </div>
        </div>

        <template v-else>
          <div>
            <div class="text-body font-semibold text-ink-2">{{ entry.title }}</div>
            <div class="tnum mt-0.5 text-[36px] font-bold leading-[1.2] tracking-[-0.02em]" :style="{ color: valueColor }">
              {{ entry.value_text }}
            </div>
            <div v-if="entry.sub" class="mt-0.5 text-small text-ink-3">{{ entry.sub }}</div>
          </div>

          <section class="flex flex-col gap-1.5">
            <div class="text-caption font-bold text-ink-2">계산식</div>
            <!-- 첨자는 유니코드(ᵢ ₖ) — 고정폭 폰트를 쓰지 않는다 -->
            <div class="whitespace-pre-line rounded bg-bg px-3.5 py-3 font-sans text-body font-medium leading-[1.75] text-ink">
              {{ entry.formula }}
            </div>
          </section>

          <section v-if="entry.columns.length" class="flex flex-col gap-1.5">
            <div class="text-caption font-bold text-ink-2">입력값</div>
            <div class="overflow-hidden rounded border border-line">
              <div class="rp-thead grid gap-2 px-3 py-[7px]" :style="{ gridTemplateColumns: gridTemplate }">
                <span v-for="(c, i) in entry.columns" :key="i" :style="{ textAlign: i === 0 ? 'left' : 'right' }">{{ c }}</span>
              </div>
              <div
                v-for="(row, r) in entry.rows"
                :key="r"
                class="tnum grid gap-2 border-t border-line-subtle px-3 py-[7px] text-small"
                :style="{ gridTemplateColumns: gridTemplate }"
              >
                <span v-for="(cell, i) in row" :key="i" class="min-w-0 break-words" :style="cellStyle(cell, i)">{{ cell.v }}</span>
              </div>
            </div>
            <div v-if="entry.note" class="text-caption font-normal leading-normal text-ink-3">{{ entry.note }}</div>
          </section>

          <section v-if="log && log.sources.length" class="flex flex-col gap-1.5">
            <div class="text-caption font-bold text-ink-2">데이터 출처</div>
            <div
              v-for="s in log.sources"
              :key="s.name"
              class="flex items-center justify-between gap-3 border-b border-line-subtle py-1.5 text-small"
            >
              <span class="flex min-w-0 items-center gap-1.5">
                <span>{{ s.name }}</span>
                <RpBadge
                  v-if="s.synthetic"
                  variant="warn"
                  tooltip="수집기가 API 키로 실행되기 전까지 데모용 합성 시계열을 사용합니다."
                  >합성</RpBadge
                >
              </span>
              <span class="tnum whitespace-nowrap text-ink-3">수집 {{ formatDate(s.collected_at) }}</span>
            </div>
          </section>

          <div v-if="log" class="mt-auto break-all font-mono text-[11px] text-ink-4">
            calc_id {{ log.calc_id }} · engine v{{ log.engine_version }}<template v-if="hashShort"> ({{ hashShort }})</template>
          </div>
        </template>
      </aside>
    </div>
  </Teleport>
</template>
