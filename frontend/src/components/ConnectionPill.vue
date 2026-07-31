<script setup lang="ts">
import { computed, onScopeDispose, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import BfChip from '@/lib/primitives/BfChip.vue';
import { useLiveStore } from '@/stores/live';

const { t } = useI18n();
const live = useLiveStore();

// Ticking countdown for the reconnect pill.
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
  <!-- Healthy is the norm: live collapses to a plain dot (label on hover).
       Anything else deserves words. -->
  <span v-if="live.connection === 'live'" class="live-dot" :title="label">
    <span class="sr-only">{{ label }}</span>
  </span>
  <BfChip v-else :tone="tone" mono>
    <span class="dot" aria-hidden="true" />
    {{ label }}
  </BfChip>
</template>

<style scoped>
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--bf-status-up);
  box-shadow: 0 0 6px color-mix(in srgb, var(--bf-status-up) 60%, transparent);
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
