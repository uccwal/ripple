<script setup lang="ts">
import { computed } from 'vue'
import { reportUrl } from '@/api/client'
import type { RunState } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import RpButton from '@/components/common/RpButton.vue'
import { useUiStore } from '@/stores/ui'
import { formatDate } from '@/utils/format'
import { hasSourcesSection, renderReport } from '@/utils/report'

/** 탭④ 보고서 — 문서형 미리보기 (max-width 820). 본문은 report.markdown 을 정리(DOMPurify)해 그린다. */
const props = defineProps<{ run: RunState }>()
const ui = useUiStore()

const report = computed(() => props.run.report)

const html = computed(() => (report.value ? renderReport(report.value.markdown) : ''))
const showCitations = computed(() => !!report.value && report.value.citations.length > 0 && !hasSourcesSection(report.value.markdown))

const validationText = computed(() => {
  const v = props.run.validation
  if (!v) return '검증 결과 없음'
  return v.status === 'fail' ? '검증 실패' : v.status === 'warn' ? '검증 통과 (경고)' : '검증 통과'
})

function onBodyClick(ev: MouseEvent): void {
  const target = (ev.target as HTMLElement | null)?.closest<HTMLElement>('[data-calc-key]')
  const key = target?.dataset.calcKey
  if (key) ui.openCalc(props.run.run_id, key)
}

function openPrintable(): void {
  window.open(reportUrl(props.run.run_id, 'html'), '_blank', 'noopener')
}
</script>

<template>
  <EmptyState
    v-if="!report"
    title="보고서가 없습니다"
    description="Report Writer 단계가 완료되지 않았습니다. 실행 과정에서 실패한 단계를 확인하세요."
  />
  <div v-else class="flex justify-center">
    <article class="w-full max-w-[820px] rounded-card border border-line bg-surface shadow-paper">
      <div class="flex items-center gap-2 border-b border-line-subtle px-5 py-3">
        <span class="text-caption font-normal text-ink-3">보고서 미리보기 · 인용 {{ report.citations.length }}건 · 모든 수치 calc_log 참조</span>
        <a
          :href="reportUrl(run.run_id, 'md')"
          :download="`${run.run_id}.md`"
          class="ml-auto inline-flex h-8 flex-none items-center whitespace-nowrap rounded border border-line-strong bg-white px-3 text-caption font-semibold text-ink no-underline hover:bg-bg hover:text-ink"
          >Markdown</a
        >
        <RpButton size="sm" class="!px-3.5 !text-caption" @click="openPrintable">PDF 다운로드</RpButton>
      </div>

      <div class="flex flex-col gap-7 px-14 pb-12 pt-10">
        <header class="border-b-2 border-navy-900 pb-4">
          <div class="text-caption font-bold tracking-[0.12em] text-navy-900">RIPPLE 정책 파급 분석 보고서</div>
          <h2 class="m-0 mt-1.5 text-title font-bold tracking-[-0.02em]">{{ run.title }}</h2>
          <div class="tnum mt-1.5 text-caption font-normal text-ink-3">
            {{ run.run_id }} · {{ formatDate(run.as_of) }} · {{ run.portfolio.name }} · 분석 기간 {{ run.horizon_days }}영업일 · {{ validationText }}
          </div>
        </header>

        <!-- v-html: renderReport()가 DOMPurify로 정리한 HTML -->
        <div class="rp-report" @click="onBodyClick" v-html="html" />

        <section v-if="showCitations" class="flex flex-col gap-1.5">
          <h3 class="m-0 text-[15px] font-bold">데이터 출처</h3>
          <ol class="m-0 list-none p-0 text-caption font-normal leading-[1.8] text-ink-2">
            <li v-for="c in report.citations" :key="c.n">
              [{{ c.n }}]
              <a v-if="c.url" :href="c.url" target="_blank" rel="noopener noreferrer" class="text-ink-2">{{ c.name }}</a>
              <template v-else>{{ c.name }}</template>
              (수집 {{ formatDate(c.collected_at) }})
            </li>
          </ol>
        </section>
      </div>
    </article>
  </div>
</template>

<style scoped>
/* 보고서 본문: 프로토타입 탭④ 타이포그래피 (섹션 15px/700, 본문 14px/1.75 #2A3140, 표 13px tnum) */
.rp-report {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 14px;
  line-height: 1.75;
  color: theme('colors.ink.report');
}
.rp-report :deep(h2) {
  margin: 20px 0 0;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.5;
  color: theme('colors.ink.DEFAULT');
}
.rp-report :deep(h2:first-child) {
  margin-top: 0;
}
.rp-report :deep(h3) {
  margin: 8px 0 0;
  font-size: 14px;
  font-weight: 700;
  color: theme('colors.ink.DEFAULT');
}
.rp-report :deep(p) {
  margin: 0;
}
.rp-report :deep(ul),
.rp-report :deep(ol) {
  margin: 0;
  padding-left: 22px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rp-report :deep(ol) {
  list-style: decimal;
}
.rp-report :deep(ul) {
  list-style: disc;
}
.rp-report :deep(li::marker) {
  color: theme('colors.ink.3');
}
.rp-report :deep(strong) {
  font-weight: 700;
  color: theme('colors.ink.DEFAULT');
}
.rp-report :deep(code) {
  font-family: theme('fontFamily.mono');
  font-size: 12px;
  background: theme('colors.bg');
  border-radius: 3px;
  padding: 1px 4px;
}
.rp-report :deep(table) {
  width: 100%;
  border-collapse: collapse;
  border-top: 1px solid theme('colors.ink.DEFAULT');
  font-size: 13px;
  line-height: 1.5;
  font-variant-numeric: tabular-nums;
}
.rp-report :deep(th) {
  padding: 6px 12px 6px 0;
  font-weight: 400;
  color: theme('colors.ink.3');
  border-bottom: 1px solid theme('colors.line.DEFAULT');
  text-align: left;
}
.rp-report :deep(td) {
  padding: 6px 12px 6px 0;
  border-bottom: 1px solid theme('colors.line.subtle');
  text-align: left;
}
.rp-report :deep(.rp-num-col) {
  text-align: right;
  white-space: nowrap;
}
.rp-report :deep(th:last-child),
.rp-report :deep(td:last-child) {
  padding-right: 0;
}
.rp-report :deep(button.rp-report-pnl),
.rp-report :deep(span.rp-report-pnl) {
  font-weight: 700;
}
.rp-report :deep(.rp-report-val) {
  font-variant-numeric: tabular-nums;
}
.rp-report :deep(blockquote),
.rp-report :deep(.rp-report-hedge:is(ul, ol) > li) {
  margin: 0;
  padding: 12px 14px;
  background: theme('colors.bg');
  border-radius: 6px;
  list-style: none;
}
.rp-report :deep(.rp-report-hedge:is(ul, ol)) {
  padding-left: 0;
  gap: 8px;
}
.rp-report :deep(.rp-report-sources) {
  font-size: 12px;
  line-height: 1.8;
  color: theme('colors.ink.2');
}
.rp-report :deep(.rp-report-sources:is(ul, ol)) {
  gap: 0;
}
.rp-report :deep(hr) {
  border: 0;
  border-top: 1px solid theme('colors.line.subtle');
  margin: 8px 0;
}
.rp-report :deep(.rp-report-num) {
  appearance: none;
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  color: inherit;
  cursor: pointer;
  font-variant-numeric: tabular-nums;
  text-decoration: underline dotted;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}
</style>
