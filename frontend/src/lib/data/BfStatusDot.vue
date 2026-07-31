<script setup lang="ts">
import { computed } from 'vue';

import { desyncMs } from '@/composables/useDesync';
import { statusToken } from '@/tokens';

const props = withDefaults(
  defineProps<{
    status: string;
    /** Stable id used to desynchronize the pulse across nodes. */
    desyncId?: string;
    size?: number;
  }>(),
  { desyncId: '', size: 10 },
);

const tone = computed(() => statusToken[props.status] ?? 'unknown');
const alive = computed(() => props.status === 'online');
const style = computed(() => ({
  '--dot-size': `${props.size}px`,
  '--dot-color': `var(--bf-status-${tone.value})`,
  '--bf-desync': `${desyncMs(props.desyncId)}`,
}));
</script>

<template>
  <span
    class="bf-status-dot"
    :class="{ alive, collapsed: !alive }"
    :style="style"
    role="status"
    :aria-label="status"
  />
</template>

<style scoped>
.bf-status-dot {
  position: relative;
  display: inline-block;
  width: var(--dot-size);
  height: var(--dot-size);
  border-radius: 50%;
  background: var(--dot-color);
  transition: background-color var(--bf-dur-500);
  flex: none;
}
/* Concentric heartbeat rings; negative delay from the node-id hash keeps
   neighbours out of phase so the section breathes organically. */
.alive::before,
.alive::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: var(--dot-color);
  animation: bf-pulse 2.4s ease-out infinite;
  animation-delay: calc(var(--bf-desync, 0) * -1ms);
}
.alive::after {
  animation-delay: calc(var(--bf-desync, 0) * -1ms - 1200ms);
}
/* Downed: the heartbeat collapses instead of vanishing. */
.collapsed {
  transform: scale(0.85);
  transition:
    transform var(--bf-dur-300) var(--bf-ease-spring),
    background-color var(--bf-dur-500);
}
</style>
