<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useUiStore } from '@/stores/ui'

/** 토스트: 하단 중앙 28px, navy-900, 흰 13px/600, radius 6, 3.2초 */
const { toast } = storeToRefs(useUiStore())
</script>

<template>
  <Teleport to="body">
    <div
      v-if="toast"
      :key="toast.id"
      class="fixed bottom-7 left-1/2 z-[60] -translate-x-1/2 rounded bg-navy-900 px-[18px] py-2.5 text-small font-semibold text-white shadow-toast"
      role="status"
      aria-live="polite"
    >
      {{ toast.message }}
    </div>
  </Teleport>
</template>
