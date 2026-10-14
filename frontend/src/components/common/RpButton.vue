<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

/**
 * README "버튼"
 * - primary: 높이 36, 패딩 0 16, 배경 navy-900, hover navy-700 · 큰 버튼(lg) 44 / 0 28 / 15px 700
 * - secondary: 높이 36, 패딩 0 14, 1px #CDD2DA, hover #F5F6F8
 * - outline: 1px navy-900, 글자 navy-900, hover navy-50
 * - 비활성: primary는 배경 #A3AAB6, 그 외는 opacity .45
 */
const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'outline'
    size?: 'sm' | 'md' | 'lg'
    disabled?: boolean
    to?: RouteLocationRaw
    href?: string
    type?: 'button' | 'submit'
  }>(),
  { variant: 'primary', size: 'md', disabled: false, type: 'button' },
)

const classes = computed(() => {
  const base =
    'inline-flex items-center justify-center gap-1.5 whitespace-nowrap flex-none rounded font-semibold no-underline transition-none'
  const size = {
    sm: 'h-8 px-3.5 text-small',
    md: 'h-9 text-small ' + (props.variant === 'primary' ? 'px-4' : 'px-3.5'),
    lg: 'h-11 px-7 text-[15px] font-bold',
  }[props.size]
  const variant = {
    primary: props.disabled
      ? 'border-0 bg-ink-4 text-white cursor-not-allowed'
      : 'border-0 bg-navy-900 text-white hover:bg-navy-700 hover:text-white cursor-pointer',
    secondary:
      'border border-line-strong bg-surface text-ink ' +
      (props.disabled ? 'opacity-45 cursor-not-allowed' : 'hover:bg-bg hover:text-ink cursor-pointer'),
    outline:
      'border border-navy-900 bg-surface text-navy-900 ' +
      (props.disabled ? 'opacity-45 cursor-not-allowed' : 'hover:bg-navy-50 hover:text-navy-900 cursor-pointer'),
  }[props.variant]
  return [base, size, variant]
})
</script>

<template>
  <RouterLink v-if="to && !disabled" :to="to" :class="classes"><slot /></RouterLink>
  <a v-else-if="href && !disabled" :href="href" :class="classes"><slot /></a>
  <button v-else :type="type" :disabled="disabled" :class="classes"><slot /></button>
</template>
