<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import BfNumberRoll from '@/lib/data/BfNumberRoll.vue';
import BfSkeleton from '@/lib/structural/BfSkeleton.vue';

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

// WMO weather codes → one of our hand-drawn icons.
const icon = computed(() => {
  const code = data.value?.weather_code ?? -1;
  if (code === 0) return 'sun';
  if (code <= 3) return 'cloud';
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return 'snow';
  if (code >= 51) return 'rain';
  return 'cloud';
});
</script>

<template>
  <div class="weather">
    <template v-if="data">
      <!-- Hand-animated SVG, no libraries: rays rotate, drops fall. -->
      <svg viewBox="0 0 48 48" class="icon" aria-hidden="true">
        <g v-if="icon === 'sun'">
          <circle cx="24" cy="24" r="9" class="sun-core" />
          <g class="rays">
            <line v-for="n in 8" :key="n" x1="24" y1="6" x2="24" y2="11"
              class="ray" :transform="`rotate(${(n - 1) * 45} 24 24)`" />
          </g>
        </g>
        <g v-else>
          <path
            class="cloud-body"
            d="M14 30a7 7 0 0 1 1-13.9A9 9 0 0 1 32.5 18 6.5 6.5 0 0 1 32 31H14z"
          />
          <g v-if="icon === 'rain'" class="drops">
            <line v-for="n in 3" :key="n" class="drop" :style="{ '--d': n }"
              :x1="16 + n * 5" y1="34" :x2="14 + n * 5" y2="40" />
          </g>
          <g v-if="icon === 'snow'" class="drops">
            <circle v-for="n in 3" :key="n" class="flake" :style="{ '--d': n }"
              :cx="16 + n * 5" cy="37" r="1.6" />
          </g>
        </g>
      </svg>

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
.icon {
  width: 52px;
  height: 52px;
  overflow: visible;
}
.sun-core {
  fill: none;
  stroke: var(--bf-status-warn);
  stroke-width: 2;
}
.rays {
  transform-origin: 24px 24px;
  animation: bf-rotate 60s linear infinite;
}
.ray {
  stroke: var(--bf-status-warn);
  stroke-width: 2;
  stroke-linecap: round;
}
@keyframes bf-rotate {
  to {
    transform: rotate(360deg);
  }
}
.cloud-body {
  fill: none;
  stroke: var(--bf-ink-secondary);
  stroke-width: 2;
  stroke-linejoin: round;
}
.drop {
  stroke: var(--bf-metric-net-rx);
  stroke-width: 2;
  stroke-linecap: round;
  animation: bf-fall 1.4s ease-in infinite;
  animation-delay: calc(var(--d) * -0.45s);
}
.flake {
  fill: var(--bf-ink-secondary);
  animation: bf-fall 2.2s linear infinite;
  animation-delay: calc(var(--d) * -0.7s);
}
@keyframes bf-fall {
  from {
    transform: translateY(-2px);
    opacity: 1;
  }
  to {
    transform: translateY(6px);
    opacity: 0;
  }
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
