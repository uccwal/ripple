<script setup lang="ts">
/** 스켈레톤 막대 — 기본 #EEF0F3, strong #E7EAEE, block #F0F2F5 */
withDefaults(
  defineProps<{ w?: string; h?: number; tone?: 'base' | 'strong' | 'block'; radius?: number }>(),
  { w: '100%', h: 10, tone: 'base', radius: 3 },
)
</script>

<template>
  <div
    aria-hidden="true"
    :class="{ 'bg-skel': tone === 'base', 'bg-skel-strong': tone === 'strong', 'bg-skel-block': tone === 'block' }"
    :style="{ width: w, height: `${h}px`, borderRadius: `${radius}px` }"
  />
</template>
