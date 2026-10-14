<script setup lang="ts">
import { computed } from 'vue'
import { BaseEdge, EdgeLabelRenderer } from '@vue-flow/core'
import { MINUS } from '@/utils/format'
import { EDGE_STYLE } from '@/utils/labels'
import { edgePath } from './layout'
import type { FlowEdgeData } from './types'

/**
 * 파급 경로 엣지: 수평 접선 베지어 · 확신도별 선 (높음 실선 2.5 navy / 중간 실선 2 #8C9AB8 / 낮음 점선 1.5 #A3AAB6 5 4)
 * 중점에 20px 원 라벨 (같은 색 1.5px 테두리, 낮음은 점선) + 부호 13px/700
 */
const props = defineProps<{
  id: string
  sourceX: number
  sourceY: number
  targetX: number
  targetY: number
  data: FlowEdgeData
}>()

const style = computed(() => EDGE_STYLE[props.data.confidence])
const path = computed(() => edgePath(props.sourceX, props.sourceY, props.targetX, props.targetY, props.data.canvasWidth))
const sign = computed(() => (props.data.direction === '-' ? MINUS : '+'))
</script>

<template>
  <BaseEdge
    :id="id"
    :path="path.d"
    :interaction-width="0"
    :style="{
      stroke: style.stroke,
      strokeWidth: style.width,
      strokeDasharray: style.dash ?? undefined,
      fill: 'none',
    }"
  />
  <EdgeLabelRenderer>
    <div
      class="absolute flex h-5 w-5 items-center justify-center rounded-full bg-white text-[13px] font-bold leading-none"
      :style="{
        transform: `translate(-50%, -50%) translate(${path.mx}px, ${path.my}px)`,
        border: `1.5px ${style.dash ? 'dashed' : 'solid'} ${style.stroke}`,
        color: style.labelColor,
      }"
      :aria-label="`영향 방향 ${data.direction === '-' ? '음' : '양'}`"
    >
      {{ sign }}
    </div>
  </EdgeLabelRenderer>
</template>
