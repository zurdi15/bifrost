<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import ContainerCard from '@/components/ContainerCard.vue';
import SortableList from '@/components/SortableList.vue';
import type { ContainerInfo } from '@/api/types';
import { useDashboardStore } from '@/stores/dashboard';
import { useLayoutStore } from '@/stores/layout';
import { useLiveStore } from '@/stores/live';

// embedded: rendered under the dashboard tabs, which already label it.
// Grouping/filter/search state lives in the dashboard store — the toolbar
// that drives it is owned by DashboardView and shared across tabs.
withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false });

const { t } = useI18n();
const live = useLiveStore();
const layout = useLayoutStore();
const dash = useDashboardStore();

// Stable per-service id: names survive container recreation, ids don't.
const serviceId = (container: ContainerInfo): string =>
  `${container.node_uuid}:${container.name}`;

const matchesQuery = (container: ContainerInfo): boolean =>
  !dash.needle ||
  [container.meta.name, container.name, container.node_name, container.meta.group].some(
    (field) => field?.toLowerCase().includes(dash.needle),
  );

const filtered = computed(() =>
  [...live.containerList, ...(dash.showHidden ? live.hiddenContainers : [])].filter(
    (c) => (!dash.nodeFilter || c.node_uuid === dash.nodeFilter) && matchesQuery(c),
  ),
);

interface Bucket {
  key: string;
  label: string;
  list: ContainerInfo[];
}

// Buckets by the active mode. Only the label-group view is drag-orderable:
// that's the canonical layout the saved order belongs to.
const groups = computed<Bucket[]>(() => {
  const map = new Map<string, ContainerInfo[]>();
  const keyOf = (container: ContainerInfo): string => {
    switch (dash.groupMode) {
      case 'node':
        return container.node_name;
      case 'state':
        return container.state === 'running' ? 'running' : 'stopped';
      default:
        return container.meta.group ?? '';
    }
  };
  for (const container of filtered.value) {
    const key = keyOf(container);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(container);
  }
  switch (dash.groupMode) {
    case 'node':
      return [...map.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, list]) => ({ key, label: key, list }));
    case 'state':
      return (['running', 'stopped'] as const)
        .filter((key) => map.has(key))
        .map((key) => ({ key, label: t(`services.${key}`), list: map.get(key)! }));
    default:
      return [...map.entries()]
        .sort(([a], [b]) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)))
        .map(([key, list]) => ({
          key,
          label: key,
          list: layout.apply(`svc:${key}`, list, serviceId),
        }));
  }
});
</script>

<template>
  <section
    v-if="embedded || live.containerList.length > 0 || live.hiddenContainers.length > 0"
    class="services"
  >
    <header v-if="!embedded" class="section-head">
      <h2 class="title">{{ t('services.title') }}</h2>
    </header>

    <p
      v-if="live.containerList.length === 0 && live.hiddenContainers.length === 0"
      class="empty"
    >
      {{ t('services.empty') }}
    </p>
    <p v-else-if="filtered.length === 0" class="empty">
      {{ t('services.noMatches') }}
    </p>

    <div v-for="(bucket, gi) in groups" :key="bucket.key || '_'" class="group">
      <h3 v-if="bucket.label" class="group-title">{{ bucket.label }}</h3>
      <SortableList
        class="grid bf-stagger"
        :items="bucket.list"
        :id-of="serviceId"
        :disabled="dash.groupMode !== 'group' || dash.needle !== ''"
        @reorder="(ids) => layout.setOrder(`svc:${bucket.key}`, ids)"
      >
        <template #item="{ element: container, index: i }">
          <ContainerCard
            :container="container"
            :class="{ dimmed: container.meta.hide }"
            :style="{ '--i': gi + i }"
          />
        </template>
      </SortableList>
    </div>
  </section>
</template>

<style scoped>
.services {
  margin-top: 0;
}
.section-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0 1.1rem;
}
.title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--bf-ink-secondary);
}
.dimmed {
  opacity: 0.55;
}
.empty {
  color: var(--bf-ink-muted);
  font-size: 0.85rem;
}
/* Breathing room between a group and the next (incl. the ungrouped tail). */
.group + .group {
  margin-top: 1.4rem;
}
.group-title {
  margin: 1rem 0 0.6rem;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--bf-ink-muted);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 0.75rem;
}
</style>
