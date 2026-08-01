<script setup lang="ts">
import { onMounted, onScopeDispose, ref } from 'vue';

import WeatherGlyph from '@/widgets/weather/Glyph.vue';

interface WeatherData {
  temp: number | null;
  weather_code: number | null;
  wind_kmh: number | null;
  humidity_pct: number | null;
  temp_max: number | null;
  temp_min: number | null;
}

// Mirrors the dashboard weather widget: same source, same data, compact.
// Renders nothing until a weather widget exists (that's where the location
// is configured).
const data = ref<WeatherData | null>(null);
let widgetId: number | null = null;

async function load(): Promise<void> {
  try {
    if (widgetId === null) {
      const rows: { id: number; type: string }[] = await (
        await fetch('/api/v1/widgets')
      ).json();
      widgetId = rows.find((row) => row.type === 'weather')?.id ?? null;
    }
    if (widgetId === null) {
      data.value = null;
      return;
    }
    const response = await fetch(`/api/v1/widgets/${widgetId}/data`);
    if (!response.ok) throw new Error(String(response.status));
    data.value = (await response.json()).data;
  } catch {
    // Widget deleted or hub hiccup: hide and re-resolve on the next tick.
    data.value = null;
    widgetId = null;
  }
}

onMounted(load);
const timer = setInterval(load, 10 * 60 * 1000);
onScopeDispose(() => clearInterval(timer));
</script>

<template>
  <div v-if="data" class="weather">
    <WeatherGlyph :code="data.weather_code" :size="24" />
    <span class="temp bf-metric">{{ (data.temp ?? 0).toFixed(0) }}°</span>
    <span class="detail bf-metric">
      <span class="range">↑{{ data.temp_max?.toFixed(0) }}° ↓{{ data.temp_min?.toFixed(0) }}°</span>
      <span class="extra">
        {{ data.humidity_pct?.toFixed(0) }}% · {{ data.wind_kmh?.toFixed(0) }} km/h
      </span>
    </span>
  </div>
</template>

<style scoped>
.weather {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
.temp {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--bf-ink-strong);
}
.detail {
  display: flex;
  flex-direction: column;
  gap: 0.05rem;
  line-height: 1.1;
}
.range {
  font-size: 0.6rem;
  color: var(--bf-ink-secondary);
}
.extra {
  font-size: 0.58rem;
  color: var(--bf-ink-muted);
}
@media (max-width: 480px) {
  .detail {
    display: none;
  }
}
</style>
