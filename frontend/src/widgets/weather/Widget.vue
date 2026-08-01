<script setup lang="ts">
import { onMounted, onScopeDispose, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import BfNumberRoll from '@/lib/data/BfNumberRoll.vue';
import BfSkeleton from '@/lib/structural/BfSkeleton.vue';
import WeatherGlyph from './Glyph.vue';

interface WeatherData {
  temp: number | null;
  weather_code: number | null;
  wind_kmh: number | null;
  humidity_pct: number | null;
  temp_max: number | null;
  temp_min: number | null;
}

const props = defineProps<{ widgetId: number; config: Record<string, unknown> }>();

const { t } = useI18n();
const data = ref<WeatherData | null>(null);
const failed = ref(false);

async function load(): Promise<void> {
  try {
    const response = await fetch(`/api/v1/widgets/${props.widgetId}/data`);
    if (!response.ok) throw new Error(String(response.status));
    data.value = (await response.json()).data;
    failed.value = false;
  } catch {
    failed.value = true;
  }
}

onMounted(load);
const timer = setInterval(load, 10 * 60 * 1000);
onScopeDispose(() => clearInterval(timer));
</script>

<template>
  <div class="weather">
    <template v-if="data">
      <WeatherGlyph :code="data.weather_code" :size="52" />

      <div class="reading">
        <span class="temp">
          <BfNumberRoll :value="data.temp ?? 0" :decimals="0" suffix="°" />
        </span>
        <span class="range bf-metric">
          ↑{{ data.temp_max?.toFixed(0) }}° ↓{{ data.temp_min?.toFixed(0) }}°
        </span>
        <span class="extra bf-metric">
          {{ data.humidity_pct?.toFixed(0) }}% · {{ data.wind_kmh?.toFixed(0) }} km/h
        </span>
      </div>
    </template>
    <p v-else-if="failed" class="error">{{ t('widgets.weatherError') }}</p>
    <div v-else class="loading">
      <BfSkeleton width="48px" height="48px" rounded="pill" />
      <BfSkeleton width="70px" height="2rem" />
    </div>
  </div>
</template>

<style scoped>
.weather {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  min-height: 90px;
}
.reading {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.temp {
  font-size: 1.9rem;
  font-weight: 600;
  color: var(--bf-ink-strong);
  line-height: 1;
}
.range {
  font-size: 0.72rem;
  color: var(--bf-ink-secondary);
}
.extra {
  font-size: 0.68rem;
  color: var(--bf-ink-muted);
}
.error {
  font-size: 0.78rem;
  color: var(--bf-ink-muted);
}
.loading {
  display: flex;
  align-items: center;
  gap: 1rem;
}
</style>
