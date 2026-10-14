<script setup lang="ts">
import { computed } from 'vue'
import type { RunState } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import RpButton from '@/components/common/RpButton.vue'
import EvidencePanel from './EvidencePanel.vue'
import ImpactGraph from './graph/ImpactGraph.vue'

const props = defineProps<{ run: RunState; selectedNodeId: string | null }>()
defineEmits<{ select: [id: string]; 'go-scenario': [] }>()

const graph = computed(() => props.run.graph)
const selectedNode = computed(() => graph.value?.nodes.find((n) => n.id === props.selectedNodeId) ?? null)
</script>

<template>
  <EmptyState
    v-if="run.entry === 'scenario'"
    title="직접 입력한 시나리오에는 파급 경로가 없습니다"
    description="시나리오 입력 시 Event Analyst와 Impact Mapper 단계를 건너뜁니다. 변환된 충격값은 시나리오 탭에서 확인할 수 있습니다."
  >
    <RpButton @click="$emit('go-scenario')">시나리오 보기</RpButton>
  </EmptyState>

  <EmptyState
    v-else-if="!graph || graph.nodes.length === 0"
    title="파급 경로가 없습니다"
    description="Impact Mapper가 이 실행에서 경로를 만들지 않았습니다. 실행 과정의 단계 메모를 확인하세요."
  />

  <div v-else class="grid grid-cols-[minmax(0,1fr)_300px] items-start gap-4">
    <ImpactGraph :graph="graph" :selected-id="selectedNodeId" :event-date="run.event?.announced_at" @select="$emit('select', $event)" />
    <EvidencePanel :node="selectedNode" />
  </div>
</template>
