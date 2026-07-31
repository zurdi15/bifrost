<script setup lang="ts">
withDefaults(
  defineProps<{
    width?: string;
    height?: string;
    rounded?: 'card' | 'ctl' | 'pill';
  }>(),
  { width: '100%', height: '1rem', rounded: 'ctl' },
);
</script>

<template>
  <div
    class="bf-skeleton"
    :class="`r-${rounded}`"
    :style="{ width, height }"
    aria-hidden="true"
  />
</template>

<style scoped>
.bf-skeleton {
  position: relative;
  overflow: hidden;
  background: var(--bf-surface-sunken);
}
.r-card {
  border-radius: var(--bf-radius-card);
}
.r-ctl {
  border-radius: var(--bf-radius-ctl);
}
.r-pill {
  border-radius: var(--bf-radius-pill);
}
.bf-skeleton::after {
  content: '';
  position: absolute;
  inset: 0;
  width: 60%;
  background: linear-gradient(105deg, transparent, var(--bf-shimmer), transparent);
  animation: bf-shimmer 1.8s ease-in-out infinite;
}
</style>
