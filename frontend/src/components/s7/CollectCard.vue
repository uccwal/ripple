<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ApiError, errorMessage } from '@/api/client'
import type { CollectReport, CollectState, CollectorStatus } from '@/api/types'
import RpBadge from '@/components/common/RpBadge.vue'
import RpButton from '@/components/common/RpButton.vue'
import RpChip from '@/components/common/RpChip.vue'
import RpSpinner from '@/components/common/RpSpinner.vue'
import { useDataStore } from '@/stores/data'
import { formatDuration, formatKst, formatRelative, summarizeCounts } from '@/utils/dataStatus'
import { COLLECT_REPORT_BADGE } from '@/utils/labels'

/**
 * S7 수집 실행 카드
 * - 관리 토큰(localStorage `ripple.adminToken`) · 기간 · 수집기 선택 → POST /api/admin/collect
 * - 진행 중이면 보고서가 도착하는 대로 로그를 보여주고, 끝나면 마지막 결과를 유지한다.
 */
const props = defineProps<{ adminEnabled: boolean; collectors: CollectorStatus[]; collect: CollectState; now: number }>()
const emit = defineEmits<{ started: [] }>()

const TOKEN_KEY = 'ripple.adminToken'
const SINCE_OPTIONS = [
  { value: '30d', label: '최근 30일' },
  { value: '1y', label: '최근 1년' },
  { value: 'all', label: '전체 (2015~)' },
] as const
type SinceKey = (typeof SINCE_OPTIONS)[number]['value']

function readToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}
function saveToken(v: string): void {
  try {
    if (v) localStorage.setItem(TOKEN_KEY, v)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* 사생활 보호 모드 등 — 기억하지 못해도 동작한다 */
  }
}

const store = useDataStore()
const token = ref(readToken())
const since = ref<SinceKey>('30d')
const selected = ref<Set<string>>(new Set(props.collectors.map((c) => c.name)))
const submitting = ref(false)
const formError = ref<string | null>(null)

// 수집기 목록이 바뀌면(첫 로드 등) 새 수집기를 선택 상태에 포함한다.
watch(
  () => props.collectors.map((c) => c.name),
  (names, prev) => {
    const prevSet = new Set(prev ?? [])
    for (const n of names) if (!prevSet.has(n)) selected.value.add(n)
    for (const n of [...selected.value]) if (!names.includes(n)) selected.value.delete(n)
    selected.value = new Set(selected.value)
  },
)
watch(token, saveToken)

const running = computed(() => props.collect.running)
const canSubmit = computed(() => !submitting.value && !running.value && token.value.trim().length > 0 && selected.value.size > 0)

function toggle(name: string): void {
  const next = new Set(selected.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  selected.value = next
}

function toggleAll(): void {
  selected.value = selected.value.size === props.collectors.length ? new Set() : new Set(props.collectors.map((c) => c.name))
}

function sinceDate(key: SinceKey): string {
  if (key === 'all') return '2015-01-01'
  const days = key === '30d' ? 30 : 365
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10)
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  formError.value = null
  try {
    const only = selected.value.size === props.collectors.length ? undefined : props.collectors.map((c) => c.name).filter((n) => selected.value.has(n))
    await store.startCollect(token.value.trim(), { since: sinceDate(since.value), only })
    emit('started')
  } catch (err) {
    if (err instanceof ApiError && err.status === 403) formError.value = '토큰이 올바르지 않습니다'
    else if (err instanceof ApiError && err.status === 409) formError.value = '이미 진행 중'
    else if (err instanceof ApiError && err.status === 404) formError.value = '관리용 API가 비활성 상태입니다 (서버의 ADMIN_TOKEN 설정 필요)'
    else formError.value = errorMessage(err)
  } finally {
    submitting.value = false
  }
}

/** 보고서 목록 (도착 순) */
const reports = computed(() => props.collect.reports)
const errorCount = computed(() => reports.value.filter((r) => r.status === 'error').length + (props.collect.error ? 1 : 0))

const runMeta = computed(() => {
  const c = props.collect
  if (c.running) return { label: '진행 로그', time: `시작 ${formatRelative(c.started_at, props.now)}`, title: formatKst(c.started_at) }
  if (!c.finished_at) return { label: '마지막 수집 결과', time: '', title: '' }
  const dur = formatDuration(c.started_at, c.finished_at)
  return {
    label: '마지막 수집 결과',
    time: `${formatKst(c.finished_at)}${dur ? ` · ${dur} 소요` : ''}`,
    title: `시작 ${formatKst(c.started_at)}`,
  }
})

function detail(r: CollectReport): string {
  return r.status === 'ok' ? summarizeCounts(r.counts) || r.message : r.message
}
</script>

<template>
  <section class="rp-card flex flex-col gap-4 p-5" aria-label="수집 실행">
    <div class="flex items-center justify-between gap-3">
      <h2 class="m-0 text-body font-bold">수집 실행</h2>
      <span v-if="running" class="inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-sm bg-navy-50 px-2 text-caption font-semibold text-navy-900">
        <RpSpinner :size="10" />수집 중
      </span>
    </div>

    <p v-if="!adminEnabled" class="m-0 rounded bg-surface-sunken px-3 py-2.5 text-small text-ink-3">
      관리용 API가 비활성 상태입니다 (서버의 ADMIN_TOKEN 설정 필요)
    </p>

    <form v-else class="flex flex-col gap-3.5" @submit.prevent="submit">
      <label class="flex flex-col gap-1.5">
        <span class="rp-section-label">관리 토큰</span>
        <input
          v-model="token"
          type="password"
          class="rp-input h-9 text-body"
          autocomplete="off"
          placeholder="ADMIN_TOKEN"
          aria-describedby="admin-token-help"
        />
        <span id="admin-token-help" class="text-micro text-ink-3">이 브라우저에만 저장됩니다</span>
      </label>

      <label class="flex flex-col gap-1.5">
        <span class="rp-section-label">기간</span>
        <select v-model="since" class="rp-select h-9 text-body">
          <option v-for="o in SINCE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>

      <div class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <span class="rp-section-label">수집기</span>
          <button type="button" class="cursor-pointer border-0 bg-transparent p-0 text-caption font-semibold text-navy-900" @click="toggleAll">
            {{ selected.size === collectors.length ? '모두 해제' : '모두 선택' }}
          </button>
        </div>
        <div class="flex flex-wrap gap-2" role="group" aria-label="수집기 선택">
          <RpChip v-for="c in collectors" :key="c.name" :selected="selected.has(c.name)" :title="c.description" @click="toggle(c.name)">
            {{ c.name }}
          </RpChip>
        </div>
      </div>

      <div v-if="formError" class="rounded-sm bg-fail-bg px-2 py-1.5 text-caption font-semibold text-fail" role="alert">{{ formError }}</div>

      <div class="flex items-center gap-3">
        <RpButton type="submit" :disabled="!canSubmit">
          <RpSpinner v-if="submitting" :size="10" />
          {{ running ? '수집 진행 중' : '지금 수집' }}
        </RpButton>
        <span v-if="selected.size === 0" class="text-caption text-ink-3">수집기를 하나 이상 선택하세요</span>
        <span v-else-if="!token.trim()" class="text-caption text-ink-3">관리 토큰을 입력하세요</span>
      </div>
    </form>

    <div class="flex flex-col gap-2 border-t border-line-subtle pt-4">
      <div class="flex items-center justify-between gap-3">
        <h3 class="m-0 text-small font-bold text-ink-2">{{ runMeta.label }}</h3>
        <span v-if="runMeta.time" class="tnum whitespace-nowrap text-caption text-ink-3" :title="runMeta.title">{{ runMeta.time }}</span>
      </div>

      <div v-if="collect.error" class="rounded-sm bg-fail-bg px-2 py-1.5 text-caption text-fail" role="alert">수집 중단 · {{ collect.error }}</div>

      <ul v-if="reports.length" class="m-0 flex list-none flex-col p-0" aria-live="polite">
        <li
          v-for="(r, i) in reports"
          :key="`${r.collector}:${i}`"
          class="flex items-center gap-2.5 py-2 text-small"
          :class="i ? 'border-t border-line-subtle' : ''"
        >
          <span class="w-[118px] flex-none font-mono text-[12px] font-semibold">{{ r.collector }}</span>
          <RpBadge :variant="COLLECT_REPORT_BADGE[r.status].variant">{{ COLLECT_REPORT_BADGE[r.status].text }}</RpBadge>
          <span class="ellipsis min-w-0 flex-1 text-caption" :class="r.status === 'error' ? 'text-fail' : 'text-ink-2'" :title="r.message">
            {{ detail(r) }}
          </span>
        </li>
        <li v-if="running" class="flex items-center gap-2 border-t border-line-subtle py-2 text-caption font-semibold text-navy-900">
          <RpSpinner />다음 수집기 실행 중…
        </li>
      </ul>
      <div v-else-if="running" class="flex items-center gap-2 py-1 text-caption font-semibold text-navy-900"><RpSpinner />첫 수집기 실행 중…</div>
      <div v-else class="py-1 text-small text-ink-3">아직 수집 기록이 없습니다. 서버 기동 후 실행된 수집의 결과가 여기에 남습니다.</div>

      <div v-if="!running && reports.length" class="text-caption text-ink-3">
        {{ reports.length }}개 수집기<template v-if="errorCount"> · <span class="font-semibold text-fail">오류 {{ errorCount }}건</span></template>
      </div>
    </div>
  </section>
</template>
