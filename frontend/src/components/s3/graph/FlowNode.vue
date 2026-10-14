<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import type { FlowNodeData } from './types'

/**
 * 파급 경로 노드: 흰 배경, radius 6, 패딩 6 10, 제목 12.5px/700, 보조 11px #7A8394
 * 기본 1px #CDD2DA · 확신도 낮음 #F7F8FA + 1px dashed #A3AAB6 + "⚠ 근거 불충분"
 * 선택 2px solid #16264A + 0 0 0 3px rgba(22,38,74,.12)
 */
const props = defineProps<{ id: string; data: FlowNodeData }>()

const low = computed(() => props.data.node.confidence === 'low')
const frame = computed(() => {
  if (props.data.selected) return 'border-2 border-solid border-navy-900 shadow-focus'
  return low.value ? 'border border-dashed border-ink-4' : 'border border-solid border-line-strong'
})
</script>

<template>
  <button
    type="button"
    class="flex h-full w-full cursor-pointer flex-col justify-center overflow-hidden rounded px-2.5 py-1.5 text-left"
    :class="[frame, low ? 'bg-surface-muted' : 'bg-white']"
    :aria-pressed="data.selected"
    :title="data.node.label"
    @click="data.onSelect(id)"
  >
    <span class="line-clamp-2 text-[12.5px] font-bold leading-[1.25]" :class="low ? 'text-ink-2' : 'text-ink'">{{ data.node.label }}</span>
    <span v-if="low" class="ellipsis text-micro font-semibold text-warn">⚠ 근거 불충분</span>
    <span v-else class="ellipsis text-micro text-ink-3">{{ data.sub }}</span>
  </button>
  <Handle type="target" :position="Position.Left" :connectable="false" class="ripple-handle" />
  <Handle type="source" :position="Position.Right" :connectable="false" class="ripple-handle" />
</template>
