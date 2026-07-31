<script setup lang="ts">
import { computed } from 'vue';
import { mdiOpenInNew } from '@mdi/js';

import type { ContainerInfo } from '@/api/types';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import BfStatusDot from '@/lib/data/BfStatusDot.vue';

const props = defineProps<{ container: ContainerInfo }>();

// Container state/health → the shared node-status visual language.
const status = computed(() => {
  if (props.container.health === 'unhealthy') return 'degraded';
  switch (props.container.state) {
    case 'running':
      return 'online';
    case 'restarting':
    case 'starting':
      return 'pending';
    case 'paused':
      return 'disabled';
    default:
      return 'offline';
  }
});

const tone = computed(
  () =>
    ((
      {
        online: 'up',
        degraded: 'degraded',
        pending: 'warn',
        disabled: 'unknown',
        offline: 'down',
      } as const
    )[status.value] ?? 'unknown'),
);

const shortImage = computed(() => {
  const image = props.container.image ?? '';
  return image.split('/').pop()?.split('@')[0] ?? image;
});
</script>

<template>
  <component
    :is="container.meta.url ? 'a' : 'div'"
    :href="container.meta.url"
    target="_blank"
    rel="noreferrer"
    class="wrap"
  >
    <BfCard :interactive="!!container.meta.url" class="container-card">
      <header class="head">
        <BfStatusDot :status="status" :desync-id="container.id" :size="8" />
        <span class="name">{{ container.name }}</span>
        <BfIcon v-if="container.meta.url" :path="mdiOpenInNew" :size="13" class="ext" />
      </header>
      <p class="image bf-metric" :title="container.image ?? ''">{{ shortImage }}</p>
      <footer class="foot">
        <BfChip :tone="tone">
          {{ container.health === 'unhealthy' ? 'unhealthy' : container.state }}
        </BfChip>
        <span class="node">{{ container.node_name }}</span>
      </footer>
    </BfCard>
  </component>
</template>

<style scoped>
.wrap {
  text-decoration: none;
  color: inherit;
  display: block;
  border-radius: var(--bf-radius-card);
}
.container-card {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  padding: 0.75rem 0.85rem;
}
.head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}
.name {
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--bf-ink-strong);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ext {
  color: var(--bf-ink-faint);
}
.image {
  margin: 0;
  font-size: 0.68rem;
  color: var(--bf-ink-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.node {
  font-size: 0.68rem;
  color: var(--bf-ink-faint);
}
</style>
