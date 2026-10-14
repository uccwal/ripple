<script setup lang="ts">
import type { RunTab } from '@/stores/run'

defineProps<{ active: RunTab; scenarioDirty: boolean }>()
defineEmits<{ select: [tab: RunTab] }>()

const TABS: { key: RunTab; label: string }[] = [
  { key: 'path', label: '파급 경로' },
  { key: 'scen', label: '시나리오' },
  { key: 'result', label: '결과' },
  { key: 'report', label: '보고서' },
]
</script>

<template>
  <div class="flex gap-1 border-b border-line" role="tablist">
    <button
      v-for="t in TABS"
      :key="t.key"
      type="button"
      role="tab"
      :aria-selected="active === t.key"
      class="-mb-px flex cursor-pointer items-center gap-1.5 whitespace-nowrap border-0 border-b-2 bg-transparent px-4 py-2.5 text-body font-semibold"
      :class="active === t.key ? 'border-navy-900 text-navy-900' : 'border-transparent text-ink-3 hover:text-ink-2'"
      @click="$emit('select', t.key)"
    >
      {{ t.label }}
      <span
        v-if="t.key === 'scen' && scenarioDirty"
        class="h-1.5 w-1.5 rounded-full bg-warn-loop"
        title="적용하지 않은 충격값 수정이 있습니다"
      />
    </button>
  </div>
</template>
