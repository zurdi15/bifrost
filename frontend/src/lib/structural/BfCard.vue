<script setup lang="ts">
withDefaults(
  defineProps<{
    interactive?: boolean;
    padded?: boolean;
  }>(),
  { interactive: false, padded: true },
);
</script>

<template>
  <div class="bf-card" :class="{ interactive, padded }">
    <slot />
  </div>
</template>

<style scoped>
.bf-card {
  position: relative;
  background: var(--bf-surface);
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-card);
  transition:
    border-color var(--bf-dur-150),
    transform var(--bf-dur-150),
    box-shadow var(--bf-dur-150);
}
.padded {
  padding: 1rem;
}
.interactive {
  cursor: pointer;
}
.interactive:hover {
  border-color: var(--bf-line-hover);
  transform: translateY(-2px);
  box-shadow: var(--bf-shadow-lift);
}
</style>
