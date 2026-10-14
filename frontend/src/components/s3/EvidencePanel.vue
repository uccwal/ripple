<script setup lang="ts">
import { computed } from 'vue'
import type { GraphNode } from '@/api/types'
import RpBadge from '@/components/common/RpBadge.vue'
import { formatDate } from '@/utils/format'
import { CONFIDENCE_LABEL, LAYER_LABEL } from '@/utils/labels'

const props = defineProps<{ node: GraphNode | null }>()

const confVariant = computed(() => (props.node ? (`conf-${props.node.confidence}` as const) : 'conf-mid'))
</script>

<template>
  <aside class="rp-card flex flex-col gap-2.5 px-[18px] py-4" aria-live="polite">
    <template v-if="node">
      <div class="text-caption font-normal text-ink-3">{{ LAYER_LABEL[node.layer] }}</div>
      <div class="-mt-1.5 text-heading font-bold">{{ node.label }}</div>
      <div class="flex flex-wrap gap-1.5">
        <RpBadge :variant="confVariant">{{ CONFIDENCE_LABEL[node.confidence] }}</RpBadge>
        <RpBadge v-if="node.confidence === 'low'" variant="warn">⚠ 근거 불충분</RpBadge>
      </div>
      <div class="text-caption font-normal text-ink-2">{{ node.direction_text }}</div>
      <div class="mt-1 text-caption font-bold text-ink-2">근거 {{ node.evidence.length }}건</div>
      <div class="flex flex-col gap-2">
        <div v-for="ev in node.evidence" :key="ev.id" class="rounded border border-line-subtle bg-surface-evidence px-3 py-2.5">
          <div class="text-small leading-[1.45]">{{ ev.text }}</div>
          <div class="mt-1 text-[11px] text-ink-3">{{ ev.source }} · 수집 {{ formatDate(ev.collected_at) }}</div>
        </div>
        <div v-if="node.evidence.length === 0" class="rounded border border-dashed border-line-strong px-3 py-2.5 text-small text-ink-3">
          기록된 근거가 없습니다.
        </div>
      </div>
    </template>
    <div v-else class="text-small text-ink-3">노드를 누르면 근거를 봅니다.</div>
  </aside>
</template>
