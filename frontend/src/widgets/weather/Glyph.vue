<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(defineProps<{ code: number | null; size?: number }>(), {
  size: 52,
});

// WMO weather codes → one of our hand-drawn icons.
const icon = computed(() => {
  const code = props.code ?? -1;
  if (code === 0) return 'sun';
  if (code <= 3) return 'cloud';
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return 'snow';
  if (code >= 51) return 'rain';
  return 'cloud';
});
</script>

<template>
  <!-- Hand-animated SVG, no libraries: rays rotate, drops fall. -->
  <svg
    viewBox="0 0 48 48"
    class="icon"
    :style="{ width: `${size}px`, height: `${size}px` }"
    aria-hidden="true"
  >
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
</template>

<style scoped>
.icon {
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
</style>
