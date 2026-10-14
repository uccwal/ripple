<script setup lang="ts">
import RpSpinner from '@/components/common/RpSpinner.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'

/** 실행 중 상태: 요약 바 스켈레톤 + 현재 단계 · 그래프 모양 스켈레톤 */
defineProps<{ current: string }>()
const COLUMNS = [
  { n: 1, gap: 0 },
  { n: 2, gap: 40 },
  { n: 3, gap: 24 },
  { n: 3, gap: 24 },
]
</script>

<template>
  <div class="rp-card flex items-center gap-7 px-5 py-4" aria-busy="true">
    <div class="flex flex-col gap-2"><SkeletonBar w="110px" /><SkeletonBar w="150px" :h="26" tone="strong" :radius="4" /></div>
    <div class="flex flex-col gap-2"><SkeletonBar w="80px" /><SkeletonBar w="140px" :h="18" tone="strong" :radius="4" /></div>
    <div class="ml-auto flex items-center gap-2.5 text-small font-semibold text-navy-900" aria-live="polite">
      <RpSpinner />
      <span>{{ current }}</span>
    </div>
  </div>
  <div class="rp-card flex flex-col gap-3.5 p-5" aria-hidden="true">
    <div class="flex gap-5">
      <SkeletonBar w="64px" :h="12" tone="strong" />
      <SkeletonBar w="52px" :h="12" />
      <SkeletonBar w="40px" :h="12" />
      <SkeletonBar w="48px" :h="12" />
    </div>
    <div class="grid grid-cols-4 gap-10 py-5">
      <div v-for="(c, i) in COLUMNS" :key="i" class="flex flex-col" :class="c.n === 1 ? 'justify-center' : ''" :style="{ gap: `${c.gap}px` }">
        <SkeletonBar v-for="j in c.n" :key="j" :h="56" tone="block" :radius="6" />
      </div>
    </div>
    <div class="text-caption font-normal text-ink-3">
      각 단계가 끝나면 결과가 이 영역에 채워집니다. 수치는 Risk Engine 계산 후 Validator 검증을 통과해야 표시됩니다.
    </div>
  </div>
</template>
