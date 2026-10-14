<script setup lang="ts">
import EmptyState from '@/components/common/EmptyState.vue'
import RpButton from '@/components/common/RpButton.vue'
</script>

<template>
  <div class="mx-auto max-w-[920px] px-8 pt-16">
    <EmptyState title="페이지를 찾을 수 없습니다" description="주소를 확인하거나 이벤트 대시보드에서 다시 시작하세요.">
      <RpButton to="/">이벤트로</RpButton>
    </EmptyState>
  </div>
</template>
