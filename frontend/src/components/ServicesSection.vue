<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { mdiEyeOffOutline } from '@mdi/js';

import ContainerCard from '@/components/ContainerCard.vue';
import SortableList from '@/components/SortableList.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import type { ContainerInfo } from '@/api/types';
import { useLayoutStore } from '@/stores/layout';
import { useLiveStore } from '@/stores/live';

// embedded: rendered under the dashboard tabs, which already label it.
withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false });

const { t } = useI18n();
const live = useLiveStore();
const layout = useLayoutStore();

const nodeFilter = ref<string | null>(null);
const showHidden = ref(false);

// How the cards bucket together. A per-browser view preference, not layout.
const MODES = [
  { id: 'group', label: 'services.byGroup' },
  { id: 'node', label: 'services.byNode' },
  { id: 'state', label: 'services.byState' },
] as const;
type GroupMode = (typeof MODES)[number]['id'];
const storedMode = localStorage.getItem('bf-services-groupby') as GroupMode | null;
const groupMode = ref<GroupMode>(
  MODES.some((mode) => mode.id === storedMode) ? storedMode! : 'group',
);
watch(groupMode, (mode) => localStorage.setItem('bf-services-groupby', mode));
const modeIndex = computed(() => MODES.findIndex((mode) => mode.id === groupMode.value));

// Stable per-service id: names survive container recreation, ids don't.
const serviceId = (container: ContainerInfo): string =>
  `${container.node_uuid}:${container.name}`;

const filtered = computed(() =>
  [...live.containerList, ...(showHidden.value ? live.hiddenContainers : [])].filter(
    (c) => !nodeFilter.value || c.node_uuid === nodeFilter.value,
  ),
);
// Filter chips come from the services themselves — Docker nodes and k8s
// clusters alike.
const sources = computed(() => {
  const seen = new Map<string, string>();
  for (const container of [...live.containerList, ...live.hiddenContainers]) {
    seen.set(container.node_uuid, container.node_name);
  }
  return [...seen.entries()].map(([uuid, name]) => ({ uuid, name }));
});

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
    switch (groupMode.value) {
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
  switch (groupMode.value) {
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

function toggleNode(uuid: string): void {
  nodeFilter.value = nodeFilter.value === uuid ? null : uuid;
}
</script>

<template>
  <section
    v-if="embedded || live.containerList.length > 0 || live.hiddenContainers.length > 0"
    class="services"
  >
    <header class="section-head">
      <h2 v-if="!embedded" class="title">{{ t('services.title') }}</h2>
      <!-- Same visual language as the nav: a cluster with a gliding pill. -->
      <span
        class="modes"
        :style="{ '--i': modeIndex }"
        role="group"
        :aria-label="t('services.groupBy')"
      >
        <span class="mode-pill" aria-hidden="true" />
        <button
          v-for="mode in MODES"
          :key="mode.id"
          class="mode"
          :class="{ active: groupMode === mode.id }"
          type="button"
          :aria-pressed="groupMode === mode.id"
          @click="groupMode = mode.id"
        >
          {{ t(mode.label) }}
        </button>
      </span>
      <span class="filters">
        <button
          v-if="live.hiddenContainers.length > 0"
          class="filter"
          :class="{ active: showHidden }"
          type="button"
          @click="showHidden = !showHidden"
        >
          <BfIcon :path="mdiEyeOffOutline" :size="12" />
          {{ t('service.showHidden', { count: live.hiddenContainers.length }) }}
        </button>
        <button
          v-for="source in sources"
          :key="source.uuid"
          class="filter"
          :class="{ active: nodeFilter === source.uuid }"
          type="button"
          @click="toggleNode(source.uuid)"
        >
          {{ source.name }}
        </button>
      </span>
    </header>

    <p
      v-if="live.containerList.length === 0 && live.hiddenContainers.length === 0"
      class="empty"
    >
      {{ t('services.empty') }}
    </p>

    <div v-for="(bucket, gi) in groups" :key="bucket.key || '_'" class="group">
      <h3 v-if="bucket.label" class="group-title">{{ bucket.label }}</h3>
      <SortableList
        class="grid bf-stagger"
        :items="bucket.list"
        :id-of="serviceId"
        :disabled="groupMode !== 'group'"
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
  flex-wrap: wrap;
}
.title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--bf-ink-secondary);
}
.filters {
  display: flex;
  gap: 0.35rem;
  margin-left: auto;
}
/* Group-by cluster: fixed-width segments so the pill glides on a transform. */
.modes {
  position: relative;
  display: inline-flex;
  padding: 0.2rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-pill);
  background: color-mix(in srgb, var(--bf-surface) 72%, transparent);
}
.mode-pill {
  position: absolute;
  top: 0.2rem;
  left: 0.2rem;
  width: 4.2rem;
  height: calc(100% - 0.4rem);
  border-radius: var(--bf-radius-pill);
  background: var(--bf-brand-tint);
  transform: translateX(calc(var(--i) * 4.2rem));
  transition: transform var(--bf-dur-300) var(--bf-ease-spring);
}
.mode {
  position: relative;
  z-index: 1;
  width: 4.2rem;
  padding: 0.22rem 0;
  font: inherit;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border: none;
  background: transparent;
  color: var(--bf-ink-muted);
  cursor: pointer;
  transition: color var(--bf-dur-150);
}
.mode:hover {
  color: var(--bf-ink);
}
.mode.active {
  color: var(--bf-brand);
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
.filter {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font: inherit;
  font-size: 0.72rem;
  padding: 0.15rem 0.6rem;
  border-radius: var(--bf-radius-pill);
  border: 1px solid var(--bf-line);
  background: transparent;
  color: var(--bf-ink-muted);
  cursor: pointer;
  transition:
    color var(--bf-dur-150),
    border-color var(--bf-dur-150),
    background-color var(--bf-dur-150);
}
.filter:hover {
  border-color: var(--bf-line-hover);
  color: var(--bf-ink);
}
.filter.active {
  color: var(--bf-brand);
  border-color: var(--bf-brand);
  background: var(--bf-brand-tint);
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
