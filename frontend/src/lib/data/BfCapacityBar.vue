<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    /** 0–100 */
    value: number;
    warnAt?: number;
    dangerAt?: number;
    /** Entrance stagger index. */
    index?: number;
  }>(),
  { warnAt: 80, dangerAt: 92, index: 0 },
);

const clamped = computed(() => Math.max(0, Math.min(100, props.value)));
const tone = computed(() => {
  if (clamped.value >= props.dangerAt) return 'var(--bf-status-down)';
  if (clamped.value >= props.warnAt) return 'var(--bf-status-warn)';
  return 'var(--bf-metric-disk)';
});
</script>

<template>
  <div class="bf-capacity" role="meter" :aria-valuenow="clamped" aria-valuemin="0" aria-valuemax="100">
    <div
      class="fill"
      :style="{
        transform: `scaleX(${clamped / 100})`,
        background: tone,
        '--i': index,
      }"
    />
  </div>
</template>

<style scoped>
.bf-capacity {
  height: 6px;
  border-radius: var(--bf-radius-pill);
  background: var(--bf-surface-sunken);
  overflow: hidden;
}
.fill {
  height: 100%;
  border-radius: inherit;
  transform-origin: left center;
  animation: bf-grow-x 600ms var(--bf-ease-spring) both;
  animation-delay: calc(min(var(--i, 0), 8) * var(--bf-stagger-step));
  transition:
    transform var(--bf-dur-500) var(--bf-ease-spring),
    background-color var(--bf-dur-500);
}
@keyframes bf-grow-x {
  from {
    transform: scaleX(0);
  }
}
</style>
