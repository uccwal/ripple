<script setup lang="ts">
import tokensCss from '@/styles/tokens.css?raw'
import type { StepStatus } from '@/api/types'
import CalcNum from '@/components/common/CalcNum.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import RpBadge from '@/components/common/RpBadge.vue'
import RpButton from '@/components/common/RpButton.vue'
import RpChip from '@/components/common/RpChip.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import StepIcon from '@/components/s3/StepIcon.vue'
import { useUiStore } from '@/stores/ui'
import { MINUS } from '@/utils/format'
import { EDGE_STYLE, STEP_VISUAL } from '@/utils/labels'

/** 컴포넌트·토큰 (/system) — 개발 참고용 */
const ui = useUiStore()

const TOKENS: [string, string][] = [
  ['navy-900', '#16264A'], ['navy-700', '#2A3F6E'], ['navy-500', '#3B5185'], ['navy-50', '#EEF1F7'], ['bg', '#F5F6F8'], ['surface', '#FFFFFF'],
  ['border', '#E3E6EB'], ['border-strong', '#CDD2DA'], ['text', '#141A24'], ['text-2', '#4A5363'], ['text-3', '#7A8394'], ['conf-mid', '#8C9AB8'],
  ['gain', '#D23F31'], ['gain-bg', '#FDEDEB'], ['loss', '#1E5BD8'], ['loss-bg', '#EAF0FD'], ['pass', '#1B7F4B'], ['pass-bg', '#E5F4EC'],
  ['warn', '#8A5E00'], ['warn-bg', '#FFF4D1'], ['fail', '#B42318'], ['fail-bg', '#FDECEA'], ['conf-low', '#A3AAB6'], ['loop', '#D9A92E'],
]

const TYPE_SCALE = [
  { spec: 'display 30/36 700', cls: 'text-display font-bold tracking-[-0.02em] tnum', text: `${MINUS}3.8%` },
  { spec: 'title 22/30 700', cls: 'text-title font-bold tracking-[-0.02em]', text: '정책 이벤트' },
  { spec: 'heading 16/24 700', cls: 'text-heading font-bold', text: '반도체 수입품 관세 부과 발표' },
  { spec: 'body 14/21 400', cls: 'text-body', text: '원/달러 환율 상승 경로로 영향을 줍니다.' },
  { spec: 'small 13/20 400', cls: 'text-small text-ink-2', text: '출처 Federal Register' },
  { spec: 'caption 12/16 600', cls: 'text-caption font-semibold text-ink-3', text: '추정 범위 (95%)' },
  { spec: '수치 tnum', cls: 'text-body tnum', text: `1,240 · 0.871 · ${MINUS}12.0` },
]

const STEP_DEMO: { status: StepStatus; name: string; time: string }[] = [
  { status: 'wait', name: '대기', time: '' },
  { status: 'running', name: '실행 중', time: '…' },
  { status: 'done', name: '완료', time: '1.2s' },
  { status: 'retry', name: '재시도', time: '0.2s' },
  { status: 'failed', name: '실패', time: '30.0s' },
  { status: 'skip', name: '건너뜀', time: '' },
]

const EDGES = [
  { conf: 'high' as const, sign: MINUS, text: '높음 · 실선 2.5px · navy-900' },
  { conf: 'mid' as const, sign: '+', text: '중간 · 실선 2px · conf-mid' },
  { conf: 'low' as const, sign: '+', text: '낮음 · 점선 1.5px · 회색' },
]

async function copyCss(): Promise<void> {
  try {
    await navigator.clipboard.writeText(tokensCss)
    ui.showToast('CSS 변수를 복사했습니다')
  } catch {
    ui.showToast('클립보드에 접근할 수 없습니다')
  }
}
</script>

<template>
  <div class="mx-auto flex max-w-[1440px] flex-col gap-7 px-8 pb-16 pt-7">
    <div>
      <h1 class="m-0 text-title font-bold tracking-[-0.02em]">컴포넌트 · 토큰</h1>
      <div class="text-small text-ink-3">손익 색상은 국내식(이익 빨강 · 손실 파랑). 포인트 컬러는 딥 네이비, 나머지는 뉴트럴.</div>
    </div>

    <section class="flex flex-col gap-3">
      <h2 class="m-0 text-[15px] font-bold">색상</h2>
      <div class="grid grid-cols-6 gap-3">
        <div v-for="[name, hex] in TOKENS" :key="name" class="rp-card overflow-hidden">
          <div class="h-[52px] border-b border-line-subtle" :style="{ background: hex }" />
          <div class="px-2.5 py-2">
            <div class="text-caption font-bold">{{ name }}</div>
            <div class="font-mono text-[11px] text-ink-3">--rp-{{ name }}</div>
            <div class="font-mono text-[11px] text-ink-2">{{ hex }}</div>
          </div>
        </div>
      </div>
    </section>

    <div class="grid grid-cols-2 gap-4">
      <section class="rp-card flex flex-col gap-2.5 px-5 py-[18px]">
        <h2 class="m-0 text-[15px] font-bold">타이포그래피 · Pretendard</h2>
        <div v-for="t in TYPE_SCALE" :key="t.spec" class="flex items-baseline gap-4 border-t border-line-subtle pt-2.5">
          <span class="w-[110px] flex-none font-mono text-[11px] text-ink-3">{{ t.spec }}</span>
          <span :class="t.cls">{{ t.text }}</span>
        </div>
      </section>

      <div class="flex flex-col gap-4">
        <section class="rp-card flex flex-col gap-3 px-5 py-[18px]">
          <h2 class="m-0 text-[15px] font-bold">상태 배지 · 칩 · 버튼</h2>
          <div class="flex flex-wrap gap-2">
            <RpBadge variant="pass">✓ 검증 통과</RpBadge>
            <RpBadge variant="warn" tooltip="툴팁으로 사유를 설명합니다">⚠ 근거 불충분</RpBadge>
            <RpBadge variant="warn">경고</RpBadge>
            <RpBadge variant="fail">! 실패</RpBadge>
            <RpBadge variant="virtual">가상 포트폴리오</RpBadge>
            <RpBadge variant="entry">정책 이벤트</RpBadge>
          </div>
          <div class="flex flex-wrap gap-2">
            <RpBadge variant="conf-high">확신도 높음</RpBadge>
            <RpBadge variant="conf-mid">확신도 중간</RpBadge>
            <RpBadge variant="conf-low">확신도 낮음</RpBadge>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <RpChip :selected="true">전체</RpChip>
            <RpChip :selected="false">미국</RpChip>
            <RpButton>Primary</RpButton>
            <RpButton variant="secondary">Secondary</RpButton>
            <RpButton variant="outline">Outline</RpButton>
            <RpButton disabled>재계산</RpButton>
            <RpButton variant="secondary" disabled>되돌리기</RpButton>
          </div>
        </section>
        <section class="rp-card flex flex-col gap-3 px-5 py-[18px]">
          <h2 class="m-0 text-[15px] font-bold">수치 표시 (클릭 가능)</h2>
          <div class="flex flex-wrap items-baseline gap-7">
            <CalcNum class="text-display font-bold" :value="-3.8" :offset="5" />
            <CalcNum class="text-heading font-bold" :value="1.3" :offset="4" />
            <CalcNum class="text-body font-semibold" :value="0" />
          </div>
          <div class="text-caption font-normal text-ink-3">
            점선 밑줄 = 계산 근거 연결. 이익 #D23F31, 손실 #1E5BD8, 0은 중립 회색. 부호는 유니코드 마이너스(−) 사용.
          </div>
        </section>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-4">
      <section class="rp-card flex flex-col gap-1 px-5 py-[18px]">
        <h2 class="m-0 mb-1.5 text-[15px] font-bold">단계 타임라인 항목</h2>
        <div v-for="s in STEP_DEMO" :key="s.status" class="flex items-center gap-3 border-t border-line-subtle py-2">
          <StepIcon :status="s.status" />
          <span class="w-[140px] text-small font-bold" :style="{ color: STEP_VISUAL[s.status].nameColor }">{{ s.name }}</span>
          <span class="text-caption font-semibold" :style="{ color: STEP_VISUAL[s.status].labelColor }">{{ STEP_VISUAL[s.status].label }}</span>
          <span class="ml-auto text-caption font-normal text-ink-3">{{ s.time }}</span>
        </div>
      </section>

      <div class="flex flex-col gap-4">
        <section class="rp-card flex flex-col gap-3 px-5 py-[18px]">
          <h2 class="m-0 text-[15px] font-bold">확신도 엣지</h2>
          <div v-for="e in EDGES" :key="e.conf" class="flex items-center gap-3.5">
            <span
              class="w-[120px]"
              :style="{ borderTop: `${EDGE_STYLE[e.conf].width}px ${EDGE_STYLE[e.conf].dash ? 'dashed' : 'solid'} ${EDGE_STYLE[e.conf].stroke}` }"
            />
            <span
              class="flex h-5 w-5 items-center justify-center rounded-full text-[13px] font-bold"
              :style="{ border: `1.5px ${EDGE_STYLE[e.conf].dash ? 'dashed' : 'solid'} ${EDGE_STYLE[e.conf].stroke}`, color: EDGE_STYLE[e.conf].labelColor }"
              >{{ e.sign }}</span
            >
            <span class="text-small">{{ e.text }}</span>
          </div>
        </section>
        <section class="rp-card flex flex-col gap-3 px-5 py-[18px]">
          <h2 class="m-0 text-[15px] font-bold">공통 상태</h2>
          <div class="grid grid-cols-3 gap-3">
            <div class="flex flex-col gap-2 rounded border border-line-subtle p-3">
              <span class="text-caption font-semibold text-ink-3">로딩</span>
              <SkeletonBar w="60%" tone="strong" />
              <SkeletonBar />
              <SkeletonBar w="80%" />
            </div>
            <EmptyState compact title="데이터 없음" description="분석 기록이 없습니다" />
            <div class="flex flex-col items-start gap-2 rounded border border-fail-line p-3">
              <span class="text-caption font-semibold text-fail">실행 실패</span>
              <span class="text-caption font-normal">API 응답 시간 초과</span>
            </div>
          </div>
          <ErrorState title="데이터를 불러오지 못했습니다" message="서버에 연결할 수 없습니다." @retry="ui.showToast('다시 시도 (예시)')" />
        </section>
      </div>
    </div>

    <section class="flex flex-col gap-2 rounded-card bg-ink px-5 py-[18px]">
      <div class="flex items-center">
        <span class="text-small font-bold text-white">CSS 변수 (src/styles/tokens.css · Tailwind theme.extend와 동일)</span>
        <button
          type="button"
          class="ml-auto h-7 cursor-pointer whitespace-nowrap rounded-sm border border-ink-2 bg-transparent px-2.5 text-caption font-normal text-white"
          @click="copyCss"
        >
          복사
        </button>
      </div>
      <pre class="m-0 whitespace-pre-wrap font-mono text-[12px] leading-[1.6] text-navy-200">{{ tokensCss }}</pre>
    </section>
  </div>
</template>
