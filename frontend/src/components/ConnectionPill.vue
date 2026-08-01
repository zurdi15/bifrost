<script setup lang="ts">
import { computed, onScopeDispose, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { useLiveStore } from '@/stores/live';

const { t } = useI18n();
const live = useLiveStore();

// Ticking countdown for the reconnect tooltip.
const now = ref(Date.now());
const timer = setInterval(() => (now.value = Date.now()), 500);
onScopeDispose(() => clearInterval(timer));

const secondsLeft = computed(() =>
  live.retryAt ? Math.max(0, Math.ceil((live.retryAt - now.value) / 1000)) : 0,
);

const tone = computed(() => {
  switch (live.connection) {
    case 'live':
      return 'up';
    case 'connecting':
      return 'unknown';
    case 'reconnecting':
      return 'warn';
    default:
      return 'down';
  }
});

const label = computed(() =>
  live.connection === 'reconnecting'
    ? t('connection.reconnecting', { seconds: secondsLeft.value })
    : t(`connection.${live.connection}`),
);
</script>

<template>
  <!-- Always just a dot; the words live in the tooltip. A text chip here
       overflows the mobile topbar the moment the hub goes unreachable. -->
  <span class="conn-dot bf-tip-bl" :class="tone" :data-bf-tip="label" tabindex="0">
    <span class="sr-only">{{ label }}</span>
  </span>
</template>

<style scoped>
.conn-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.up {
  background: var(--bf-status-up);
  box-shadow: 0 0 6px color-mix(in srgb, var(--bf-status-up) 60%, transparent);
}
.warn {
  background: var(--bf-status-warn);
  box-shadow: 0 0 6px color-mix(in srgb, var(--bf-status-warn) 60%, transparent);
}
.down {
  background: var(--bf-status-down);
  box-shadow: 0 0 6px color-mix(in srgb, var(--bf-status-down) 60%, transparent);
}
.unknown {
  background: var(--bf-status-unknown);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
