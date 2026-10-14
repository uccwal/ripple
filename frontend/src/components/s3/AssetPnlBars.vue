<script setup lang="ts">
import { computed } from 'vue'
import type { AssetResult } from '@/api/types'
import CalcNum from '@/components/common/CalcNum.vue'
import { useUiStore } from '@/stores/ui'

/**
 * 자산별 손익 가로 막대 (손실 큰 순, 0 기준 양방향).
 *
 * ECharts 대신 CSS 그리드로 그린 이유: 스펙상 각 행이 "자산명(150px) · 막대 · 값(64px)" 그리드이고,
 * 행 전체 hover 배경(#F5F6F8)·행 클릭 → S5, 값은 점선 밑줄 클릭 수치(CalcNum)여야 한다.
 * 캔버스 차트로는 행 hover 배경과 점선 밑줄 텍스트, 키보드 포커스를 스펙대로 맞추기 어렵고
 * 이름/값 열과 막대의 세로 정렬도 어긋난다. 막대 자체는 단순한 비율 폭이라 CSS로 정확히 그린다.
 */
const props = defineProps<{ runId: string; assets: AssetResult[] }>()
const ui = useUiStore()

const rows = computed(() => {
  const sorted = [...props.assets].sort((a, b) => a.ret - b.ret)
  const maxAbs = Math.max(0.01, ...sorted.map((a) => Math.abs(a.ret)))
  return sorted.map((a) => ({
    ...a,
    lw: a.ret < 0 ? `${(Math.abs(a.ret) / maxAbs) * 100}%` : '0%',
    rw: a.ret > 0 ? `${(a.ret / maxAbs) * 100}%` : '0%',
  }))
})

function open(assetId: string): void {
  ui.openCalc(props.runId, `h:${assetId}`)
}
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <button
      v-for="a in rows"
      :key="a.asset_id"
      type="button"
      class="grid cursor-pointer grid-cols-[150px_minmax(0,1fr)_64px] items-center gap-2.5 rounded-sm border-0 bg-transparent py-[3px] text-left hover:bg-bg"
      :aria-label="`${a.name} 계산 근거 보기`"
      @click="open(a.asset_id)"
    >
      <span class="ellipsis text-small">{{ a.name }}</span>
      <span class="grid h-4 grid-cols-2" aria-hidden="true">
        <span class="flex justify-end border-r border-line-strong">
          <span class="rounded-l-[2px] bg-loss" :style="{ width: a.lw }" />
        </span>
        <span class="flex">
          <span class="rounded-r-[2px] bg-gain" :style="{ width: a.rw }" />
        </span>
      </span>
      <CalcNum class="text-right text-small font-bold" :value="a.ret" :interactive="false" />
    </button>
  </div>
</template>
