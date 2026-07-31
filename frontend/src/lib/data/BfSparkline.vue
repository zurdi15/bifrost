<script setup lang="ts">
import { computed, useId } from 'vue';

import { sparklinePath } from '@/composables/useSparklinePath';

const props = withDefaults(
  defineProps<{
    points: number[];
    width?: number;
    height?: number;
    min?: number;
    max?: number;
    /** CSS color, usually a metric token: 'var(--bf-metric-cpu)'. */
    color?: string;
    /** Node down: freeze, recolor to down and extend a literal flatline. */
    flatline?: boolean;
  }>(),
  {
    width: 120,
    height: 32,
    min: undefined,
    max: undefined,
    color: 'var(--bf-metric-cpu)',
    flatline: false,
  },
);

const gradientId = useId();

const geometry = computed(() =>
  sparklinePath(props.points, props.width, props.height, { min: props.min, max: props.max }),
);
const stroke = computed(() => (props.flatline ? 'var(--bf-status-down)' : props.color));
</script>

<template>
  <svg
    class="bf-sparkline"
    :viewBox="`0 0 ${width} ${height}`"
    :width="width"
    :height="height"
    preserveAspectRatio="none"
    aria-hidden="true"
  >
    <defs>
      <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" :stop-color="stroke" stop-opacity="0.22" />
        <stop offset="100%" :stop-color="stroke" stop-opacity="0" />
      </linearGradient>
    </defs>
    <template v-if="geometry.line">
      <path class="area" :d="geometry.area" :fill="`url(#${gradientId})`" />
      <path
        class="line"
        :class="{ frozen: flatline }"
        :d="geometry.line"
        :stroke="stroke"
        pathLength="1"
      />
      <!-- EKG flatline: the trace continues, flat and red, to the edge. -->
      <line
        v-if="flatline"
        class="flat"
        :x1="width"
        :y1="geometry.lastY"
        :x2="width * 1.35"
        :y2="geometry.lastY"
        :stroke="stroke"
      />
    </template>
  </svg>
</template>

<style scoped>
.bf-sparkline {
  display: block;
  overflow: visible;
}
.line {
  fill: none;
  stroke-width: 1.6;
  stroke-linejoin: round;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
  stroke-dasharray: 1;
  animation: bf-draw var(--bf-dur-800) ease-out both;
  transition: stroke var(--bf-dur-500);
}
.frozen {
  animation: none;
  stroke-dasharray: none;
}
.area {
  animation: bf-fade-in var(--bf-dur-800) ease-out both;
  animation-delay: var(--bf-dur-300);
  transition: fill var(--bf-dur-500);
}
.flat {
  stroke-width: 1.6;
  vector-effect: non-scaling-stroke;
  stroke-dasharray: 1;
  pathLength: 1;
  animation: bf-draw var(--bf-dur-500) ease-out both;
}
</style>
