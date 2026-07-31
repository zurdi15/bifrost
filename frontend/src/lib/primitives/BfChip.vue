<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'up' | 'warn' | 'degraded' | 'down' | 'unknown' | 'neutral' | 'brand';
    mono?: boolean;
  }>(),
  { tone: 'neutral', mono: false },
);
</script>

<template>
  <span class="bf-chip" :class="[`tone-${tone}`, { 'bf-metric': mono }]">
    <slot />
  </span>
</template>

<style scoped>
.bf-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35em;
  padding: 0.15rem 0.55rem;
  border-radius: var(--bf-radius-pill);
  font-size: 0.75rem;
  font-weight: 550;
  line-height: 1.4;
  border: 1px solid var(--bf-line);
  color: var(--bf-ink-secondary);
  background: var(--bf-surface-sunken);
  white-space: nowrap;
}
.tone-up {
  color: var(--bf-status-up);
  background: var(--bf-status-up-tint);
  border-color: transparent;
}
.tone-warn {
  color: var(--bf-status-warn);
  background: var(--bf-status-warn-tint);
  border-color: transparent;
}
.tone-degraded {
  color: var(--bf-status-degraded);
  background: var(--bf-status-degraded-tint);
  border-color: transparent;
}
.tone-down {
  color: var(--bf-status-down);
  background: var(--bf-status-down-tint);
  border-color: transparent;
}
.tone-unknown {
  color: var(--bf-ink-muted);
}
.tone-brand {
  color: var(--bf-brand);
  background: var(--bf-brand-tint);
  border-color: transparent;
}
</style>
