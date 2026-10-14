<script setup lang="ts">
import type { CountryCode, EventType } from '@/api/types'
import RpChip from '@/components/common/RpChip.vue'
import type { EventFilters, PeriodDays } from '@/stores/events'

const filters = defineModel<EventFilters>({ required: true })

const COUNTRIES: { value: CountryCode | 'all'; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'US', label: '미국' },
  { value: 'KR', label: '한국' },
  { value: 'EU', label: 'EU' },
  { value: 'CN', label: '중국' },
]
const TYPES: { value: EventType | 'all'; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'tariff', label: '관세' },
  { value: 'rate', label: '금리' },
  { value: 'regulation', label: '규제' },
]
const PERIODS: { value: PeriodDays; label: string }[] = [
  { value: 30, label: '최근 30일' },
  { value: 7, label: '최근 7일' },
  { value: 90, label: '최근 90일' },
]

function set<K extends keyof EventFilters>(key: K, value: EventFilters[K]): void {
  filters.value = { ...filters.value, [key]: value }
}
</script>

<template>
  <div class="rp-card flex flex-wrap items-center gap-6 px-4 py-3">
    <div class="flex items-center gap-1.5" role="group" aria-label="국가">
      <span class="mr-1 text-caption font-normal text-ink-3">국가</span>
      <RpChip v-for="c in COUNTRIES" :key="c.value" :selected="filters.country === c.value" @click="set('country', c.value)">
        {{ c.label }}
      </RpChip>
    </div>
    <div class="flex items-center gap-1.5" role="group" aria-label="유형">
      <span class="mr-1 text-caption font-normal text-ink-3">유형</span>
      <RpChip v-for="t in TYPES" :key="t.value" :selected="filters.type === t.value" @click="set('type', t.value)">
        {{ t.label }}
      </RpChip>
    </div>
    <label class="ml-auto flex items-center gap-2">
      <span class="text-caption font-normal text-ink-3">기간</span>
      <select
        class="rp-select h-[30px] text-small"
        :value="filters.period"
        @change="set('period', Number(($event.target as HTMLSelectElement).value) as PeriodDays)"
      >
        <option v-for="p in PERIODS" :key="p.value" :value="p.value">{{ p.label }}</option>
      </select>
    </label>
  </div>
</template>
