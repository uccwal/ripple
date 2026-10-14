<script setup lang="ts">
import { storeToRefs } from 'pinia'
import SkeletonBar from '@/components/common/SkeletonBar.vue'
import { useMetaStore } from '@/stores/meta'
import { formatDelta } from '@/utils/format'

const metaStore = useMetaStore()
const { meta, state, error } = storeToRefs(metaStore)
</script>

<template>
  <section class="rp-card px-5 py-[18px]">
    <h2 class="m-0 text-small font-bold text-ink-2">오늘 수집된 이벤트</h2>
    <template v-if="meta">
      <div class="mb-3 mt-1.5 flex items-baseline gap-1.5">
        <span class="tnum text-[32px] font-bold leading-[1.5]">{{ meta.today_event_count }}</span>
        <span class="text-small text-ink-3">건 · 전일 대비 {{ formatDelta(meta.today_event_delta) }}</span>
      </div>
      <ul v-if="meta.events_by_source.length" class="m-0 flex list-none flex-col gap-1.5 p-0 text-small text-ink-2">
        <li v-for="s in meta.events_by_source" :key="s.source" class="flex justify-between">
          <span>{{ s.source }}</span><span class="tnum">{{ s.count }}</span>
        </li>
      </ul>
      <div v-else class="text-small text-ink-3">오늘 수집된 발표가 없습니다.</div>
    </template>
    <div v-else-if="state === 'error'" class="mt-2 flex flex-col items-start gap-2 text-small text-ink-2">
      <span>{{ error }}</span>
      <button type="button" class="cursor-pointer border-0 bg-transparent p-0 text-caption font-semibold text-navy-900" @click="metaStore.load()">
        다시 시도
      </button>
    </div>
    <div v-else class="mt-2 flex flex-col gap-2" aria-hidden="true">
      <SkeletonBar w="64px" :h="32" tone="strong" :radius="4" />
      <SkeletonBar :h="12" />
      <SkeletonBar w="80%" :h="12" />
    </div>
  </section>
</template>
