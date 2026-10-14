<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import CalcNum from '@/components/common/CalcNum.vue'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import { useHistoryStore } from '@/stores/history'
import { formatDateTime } from '@/utils/format'
import { ENTRY_SHORT } from '@/utils/labels'

const router = useRouter()
const history = useHistoryStore()
const { runs, state, error } = storeToRefs(history)
const recent = computed(() => runs.value.slice(0, 3))

function open(id: string): void {
  void router.push({ name: 'run', params: { id } })
}
</script>

<template>
  <section class="rp-card px-5 py-[18px]">
    <div class="flex items-baseline justify-between">
      <h2 class="m-0 text-small font-bold text-ink-2">최근 분석</h2>
      <RouterLink :to="{ name: 'runs' }" class="text-caption font-normal text-navy-900 no-underline hover:underline">전체 보기</RouterLink>
    </div>
    <div class="mt-2 flex flex-col">
      <template v-if="state === 'loading' || state === 'idle'">
        <div v-for="i in 3" :key="i" class="flex items-center gap-3 border-t border-line-subtle py-2.5" aria-hidden="true">
          <div class="flex flex-1 flex-col gap-1.5"><SkeletonBar w="80%" :h="12" tone="strong" /><SkeletonBar w="50%" :h="10" /></div>
          <SkeletonBar w="44px" :h="14" />
        </div>
      </template>
      <div v-else-if="state === 'error'" class="flex flex-col items-start gap-2 border-t border-line-subtle pt-2.5 text-small text-ink-2">
        <span>{{ error }}</span>
        <button type="button" class="cursor-pointer border-0 bg-transparent p-0 text-caption font-semibold text-navy-900" @click="history.load()">다시 시도</button>
      </div>
      <div v-else-if="recent.length === 0" class="border-t border-line-subtle pt-2.5 text-small text-ink-3">아직 실행한 분석이 없습니다.</div>
      <div
        v-for="r in recent"
        v-else
        :key="r.run_id"
        class="flex cursor-pointer items-center gap-3 border-t border-line-subtle py-2.5"
        role="link"
        tabindex="0"
        @click="open(r.run_id)"
        @keydown.enter="open(r.run_id)"
      >
        <div class="min-w-0 flex-1">
          <div class="ellipsis text-small font-semibold">{{ r.title }}</div>
          <div class="tnum text-caption font-normal text-ink-3">{{ formatDateTime(r.created_at) }} · {{ ENTRY_SHORT[r.entry] }}</div>
        </div>
        <CalcNum class="text-[15px] font-bold" :value="r.portfolio_pnl" :interactive="false" />
      </div>
    </div>
  </section>
</template>
