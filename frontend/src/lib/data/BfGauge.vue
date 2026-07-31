<script setup lang="ts">
import { computed } from 'vue';

import BfNumberRoll from '@/lib/data/BfNumberRoll.vue';

const props = withDefaults(
  defineProps<{
    /** 0–100 */
    value: number;
    label?: string;
    unit?: string;
    decimals?: number;
    size?: number;
    /** CSS color for the healthy range, usually a metric token. */
    color?: string;
    warnAt?: number;
    dangerAt?: number;
  }>(),
  {
    label: '',
    unit: '%',
    decimals: 0,
    size: 84,
    color: 'var(--bf-metric-cpu)',
    warnAt: 75,
    dangerAt: 90,
  },
);

// 270° arc opening at the bottom.
const R = 42;
const CIRCUMFERENCE = 2 * Math.PI * R;
const ARC = CIRCUMFERENCE * 0.75;

const clamped = computed(() => Math.max(0, Math.min(100, props.value)));
const dashOffset = computed(() => ARC * (1 - clamped.value / 100));
const stroke = computed(() => {
  if (clamped.value >= props.dangerAt) return 'var(--bf-status-down)';
  if (clamped.value >= props.warnAt) return 'var(--bf-status-warn)';
  return props.color;
});
const tick = (pct: number) => {
  // Map 0-100 onto the 270° arc, rotated so the gap faces down.
  const angle = ((pct / 100) * 270 + 135) * (Math.PI / 180);
  const inner = R - 5;
  const outer = R + 5;
  return {
    x1: 50 + inner * Math.cos(angle),
    y1: 50 + inner * Math.sin(angle),
    x2: 50 + outer * Math.cos(angle),
    y2: 50 + outer * Math.sin(angle),
  };
};
</script>

<template>
  <div class="bf-gauge" :style="{ width: `${size}px` }">
    <svg viewBox="0 0 100 100" :width="size" :height="size" aria-hidden="true">
      <g transform="rotate(135 50 50)">
        <circle
          class="track"
          cx="50"
          cy="50"
          :r="R"
          :stroke-dasharray="`${ARC} ${CIRCUMFERENCE}`"
        />
        <circle
          class="value"
          cx="50"
          cy="50"
          :r="R"
          :stroke="stroke"
          :stroke-dasharray="`${ARC} ${CIRCUMFERENCE}`"
          :stroke-dashoffset="dashOffset"
        />
      </g>
      <line class="tick" v-bind="tick(warnAt)" />
      <line class="tick" v-bind="tick(dangerAt)" />
    </svg>
    <div class="center">
      <span class="reading">
        <BfNumberRoll :value="clamped" :decimals="decimals" :suffix="unit" />
      </span>
      <span v-if="label" class="label">{{ label }}</span>
    </div>
  </div>
</template>

<style scoped>
.bf-gauge {
  position: relative;
  display: inline-block;
}
.track,
.value {
  fill: none;
  stroke-width: 7;
  stroke-linecap: round;
}
.track {
  stroke: var(--bf-surface-sunken);
}
.value {
  transition:
    stroke-dashoffset var(--bf-dur-500) var(--bf-ease-spring),
    stroke var(--bf-dur-500);
}
.tick {
  stroke: var(--bf-line-strong);
  stroke-width: 1;
}
.center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.15rem;
}
.reading {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--bf-ink);
}
.label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--bf-ink-muted);
}
</style>
