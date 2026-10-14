<script setup lang="ts">
/** 12px 스피너 — 2px #C9D1E3, 상단 #16264A, 0.8s linear 회전 (화면의 유일한 애니메이션) */
withDefaults(defineProps<{ size?: number }>(), { size: 12 })
</script>

<template>
  <span
    class="inline-block flex-none animate-rpspin rounded-full border-2 border-navy-200 border-t-navy-900"
    :style="{ width: `${size}px`, height: `${size}px` }"
    role="status"
    aria-label="진행 중"
  />
</template>
