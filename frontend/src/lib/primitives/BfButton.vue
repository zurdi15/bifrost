<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'primary' | 'ghost';
    size?: 'sm' | 'md';
    disabled?: boolean;
  }>(),
  { variant: 'ghost', size: 'md', disabled: false },
);
</script>

<template>
  <button class="bf-btn" :class="[variant, size]" :disabled="disabled">
    <slot />
  </button>
</template>

<style scoped>
.bf-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5em;
  border: 1px solid var(--bf-line-strong);
  border-radius: var(--bf-radius-ctl);
  background: transparent;
  color: var(--bf-ink);
  font: inherit;
  font-weight: 500;
  cursor: pointer;
  transition:
    background-color var(--bf-dur-150),
    border-color var(--bf-dur-150),
    color var(--bf-dur-150),
    transform var(--bf-dur-50);
}
.bf-btn:hover:not(:disabled) {
  border-color: var(--bf-line-hover);
  background: var(--bf-surface-raised);
}
.bf-btn:active:not(:disabled) {
  transform: scale(0.97);
}
.bf-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.primary {
  background: var(--bf-brand-tint);
  border-color: transparent;
  color: var(--bf-brand);
}
.primary:hover:not(:disabled) {
  background: var(--bf-brand-tint);
  color: var(--bf-brand-hover);
  border-color: var(--bf-brand);
}
.sm {
  padding: 0.3rem 0.65rem;
  font-size: 0.8125rem;
}
.md {
  padding: 0.45rem 0.9rem;
  font-size: 0.875rem;
}
</style>
