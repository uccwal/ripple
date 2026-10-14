<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import VChart from 'vue-echarts'
import { formatWeight } from '@/utils/format'

use([PieChart, TooltipComponent, SVGRenderer])

/**
 * 구성 도넛 (ECharts): 바깥 132px, 안쪽 84px 흰 원 + 라벨. 비중 큰 순으로 팔레트 적용.
 * 스펙상 애니메이션은 스피너 하나뿐이므로 차트 애니메이션은 끈다.
 */
const PALETTE = ['#16264A', '#3B5185', '#6F84B5', '#A8B6D3', '#D5DCEA', '#8E96A3'] as const

const props = defineProps<{ title: string; items: { label: string; weight: number }[] }>()

const sorted = computed(() =>
  [...props.items]
    .sort((a, b) => b.weight - a.weight)
    .map((it, i) => ({ ...it, color: PALETTE[i % PALETTE.length]! })),
)

const option = computed<EChartsOption>(() => ({
  animation: false,
  tooltip: {
    trigger: 'item',
    transitionDuration: 0,
    borderColor: '#E3E6EB',
    padding: [6, 10],
    textStyle: { color: '#141A24', fontSize: 12, fontFamily: 'Pretendard Variable, Pretendard, sans-serif' },
    formatter: (p) => {
      const d = Array.isArray(p) ? p[0] : p
      return `${d?.name ?? ''} <b style="font-variant-numeric:tabular-nums">${formatWeight(Number(d?.value))}</b>`
    },
  },
  series: [
    {
      type: 'pie',
      radius: [42, 66],
      center: ['50%', '50%'],
      silent: false,
      label: { show: false },
      labelLine: { show: false },
      emphasis: { scale: false },
      itemStyle: { borderWidth: 0 },
      data: sorted.value.map((s) => ({ name: s.label, value: s.weight, itemStyle: { color: s.color } })),
    },
  ],
}))
</script>

<template>
  <section class="rp-card flex items-center gap-5 px-5 py-[18px]">
    <div class="relative h-[132px] w-[132px] flex-none">
      <VChart class="h-full w-full" :option="option" autoresize :aria-label="`${title} 구성`" />
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center text-small font-bold text-ink-2">{{ title }}</div>
    </div>
    <ul class="m-0 flex min-w-0 flex-1 list-none flex-col gap-1.5 p-0">
      <li v-for="s in sorted" :key="s.label" class="flex items-center gap-2 text-small">
        <span class="h-2.5 w-2.5 flex-none rounded-[2px]" :style="{ background: s.color }" />
        <span class="ellipsis flex-1">{{ s.label }}</span>
        <span class="tnum font-semibold">{{ formatWeight(s.weight) }}</span>
      </li>
    </ul>
  </section>
</template>
