<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppTopBar from '@/components/common/AppTopBar.vue'
import CalcPanel from '@/components/common/CalcPanel.vue'
import ToastHost from '@/components/common/ToastHost.vue'
import { useMetaStore } from '@/stores/meta'
import { useUiStore } from '@/stores/ui'

const meta = useMetaStore()
const ui = useUiStore()

onMounted(() => void meta.load())
// 화면을 옮기면 S5 패널은 닫는다.
useRouter().afterEach(() => ui.closeCalc())
</script>

<template>
  <div class="min-h-screen min-w-app bg-bg">
    <AppTopBar />
    <main>
      <RouterView />
    </main>
    <CalcPanel />
    <ToastHost />
  </div>
</template>
