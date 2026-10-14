<script setup lang="ts">
import SkeletonBar from '@/components/common/SkeletonBar.vue'
</script>

<template>
  <div class="rp-card flex flex-col gap-3 px-5 py-[18px]" aria-hidden="true">
    <div class="flex items-center gap-2">
      <SkeletonBar w="30px" :h="20" />
      <SkeletonBar w="40px" :h="12" />
      <SkeletonBar w="44px" :h="22" :radius="4" />
      <SkeletonBar class="ml-auto" w="72px" :h="12" />
    </div>
    <div class="flex flex-col gap-2">
      <SkeletonBar w="70%" :h="16" tone="strong" />
      <SkeletonBar w="90%" :h="12" />
    </div>
    <SkeletonBar :h="48" tone="block" :radius="6" />
    <div class="flex items-center">
      <SkeletonBar w="140px" :h="12" />
      <SkeletonBar class="ml-auto" w="76px" :h="32" :radius="6" />
    </div>
  </div>
</template>
