<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { VueFlow, type Edge, type Node } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import type { Graph, GraphNode } from '@/api/types'
import { formatDate } from '@/utils/format'
import { CONFIDENCE_LABEL, LAYERS, LAYER_LABEL } from '@/utils/labels'
import FlowEdge from './FlowEdge.vue'
import FlowNode from './FlowNode.vue'
import { layoutGraph } from './layout'
import type { FlowEdgeData, FlowNodeData } from './types'

/**
 * 파급 경로 그래프 (Vue Flow). 정적 다이어그램이므로 드래그·줌·패닝을 모두 끄고 zoom 1로 고정한다.
 * 캔버스 폭을 ResizeObserver로 재서 layout.ts 가 px 좌표를 다시 낸다.
 */
const props = defineProps<{ graph: Graph; selectedId: string | null; eventDate?: string | null }>()
const emit = defineEmits<{ select: [id: string] }>()

const canvasEl = ref<HTMLElement | null>(null)
const width = ref(0)

let ro: ResizeObserver | null = null
onMounted(() => {
  if (!canvasEl.value) return
  width.value = canvasEl.value.clientWidth
  ro = new ResizeObserver(([entry]) => {
    if (entry) width.value = Math.round(entry.contentRect.width)
  })
  ro.observe(canvasEl.value)
})
onBeforeUnmount(() => ro?.disconnect())

const layout = computed(() => (width.value > 0 ? layoutGraph(props.graph.nodes, props.graph.edges, width.value) : null))

function subtitle(n: GraphNode): string {
  if (n.layer === 'policy') return props.eventDate ? `정책 · ${formatDate(props.eventDate)}` : '정책'
  return `${CONFIDENCE_LABEL[n.confidence]} · 근거 ${n.evidence.length}`
}

const onSelect = (id: string) => emit('select', id)

const nodes = computed<Node<FlowNodeData>[]>(() => {
  const L = layout.value
  if (!L) return []
  return props.graph.nodes
    .filter((n) => L.positions[n.id])
    .map((n) => ({
      id: n.id,
      type: 'ripple',
      position: L.positions[n.id]!,
      draggable: false,
      selectable: false,
      connectable: false,
      focusable: false,
      style: { width: `${L.nodeW}px`, height: `${L.nodeH}px` },
      data: { node: n, sub: subtitle(n), selected: n.id === props.selectedId, onSelect },
    }))
})

/** 낮음 → 중간 → 높음 순으로 그려 강한 선이 위에 오도록 */
const CONF_ORDER = { low: 0, mid: 1, high: 2 } as const

const edges = computed<Edge<FlowEdgeData>[]>(() => {
  const L = layout.value
  if (!L) return []
  return [...props.graph.edges]
    .filter((e) => L.positions[e.source] && L.positions[e.target])
    .sort((a, b) => CONF_ORDER[a.confidence] - CONF_ORDER[b.confidence])
    .map((e, i) => ({
      id: `e${i}-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      type: 'ripple',
      selectable: false,
      focusable: false,
      data: { direction: e.direction, confidence: e.confidence, canvasWidth: L.width },
    }))
})

const canvasHeight = computed(() => (layout.value ? `${layout.value.height}px` : undefined))
</script>

<template>
  <div class="rp-card px-5 pb-[18px] pt-4">
    <div class="relative mb-2.5 h-[18px] text-caption font-semibold text-ink-3" aria-hidden="true">
      <span
        v-for="(layer, i) in LAYERS"
        :key="layer"
        class="absolute top-0 whitespace-nowrap"
        :style="{ left: layout ? `${layout.columnX[i]}px` : `${i * 27}%` }"
        >{{ LAYER_LABEL[layer] }}</span
      >
    </div>

    <div ref="canvasEl" class="relative w-full" :style="{ height: canvasHeight, aspectRatio: canvasHeight ? undefined : '1000 / 360' }">
      <VueFlow
        v-if="layout"
        id="impact-graph"
        class="ripple-flow"
        :nodes="nodes"
        :edges="edges"
        :default-viewport="{ x: 0, y: 0, zoom: 1 }"
        :min-zoom="1"
        :max-zoom="1"
        :nodes-draggable="false"
        :nodes-connectable="false"
        :nodes-focusable="false"
        :edges-focusable="false"
        :elements-selectable="false"
        :zoom-on-scroll="false"
        :zoom-on-pinch="false"
        :zoom-on-double-click="false"
        :pan-on-drag="false"
        :pan-on-scroll="false"
        :prevent-scrolling="false"
        :auto-connect="false"
      >
        <template #node-ripple="p">
          <FlowNode :id="p.id" :data="p.data" />
        </template>
        <template #edge-ripple="p">
          <FlowEdge :id="p.id" :source-x="p.sourceX" :source-y="p.sourceY" :target-x="p.targetX" :target-y="p.targetY" :data="p.data" />
        </template>
      </VueFlow>
    </div>

    <div class="mt-4 flex flex-wrap items-center gap-5 border-t border-line-subtle pt-3 text-caption font-normal text-ink-2">
      <span class="flex items-center gap-1.5"><span class="h-0 w-7 border-t-[2.5px] border-solid border-navy-900" />확신도 높음</span>
      <span class="flex items-center gap-1.5"><span class="h-0 w-7 border-t-2 border-solid border-conf-mid" />확신도 중간</span>
      <span class="flex items-center gap-1.5"><span class="h-0 w-7 border-t-[1.5px] border-dashed border-conf-low" />확신도 낮음 (시나리오 제외)</span>
      <span class="ml-auto text-ink-3">＋/− 원인 변수 대비 영향 방향 · 노드를 누르면 근거를 봅니다</span>
    </div>
  </div>
</template>

<style scoped>
/* 선택 노드의 3px 그림자가 캔버스 가장자리에서 잘리지 않도록 */
.ripple-flow,
.ripple-flow :deep(.vue-flow__viewport),
.ripple-flow :deep(.vue-flow__container) {
  overflow: visible;
}
.ripple-flow :deep(.vue-flow__pane) {
  cursor: default;
}
.ripple-flow :deep(.vue-flow__node) {
  cursor: default;
}
.ripple-flow :deep(.ripple-handle) {
  width: 1px;
  height: 1px;
  min-width: 0;
  min-height: 0;
  border: 0;
  background: transparent;
  opacity: 0;
  pointer-events: none;
}
</style>
