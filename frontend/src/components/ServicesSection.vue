<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import ContainerCard from '@/components/ContainerCard.vue';
import BfChip from '@/lib/primitives/BfChip.vue';
import { useLiveStore } from '@/stores/live';

const { t } = useI18n();
const live = useLiveStore();

const nodeFilter = ref<string | null>(null);

const filtered = computed(() =>
  live.containerList.filter((c) => !nodeFilter.value || c.node_uuid === nodeFilter.value),
);
const runningCount = computed(
  () => live.containerList.filter((c) => c.state === 'running').length,
);
const nodesWithContainers = computed(() =>
  live.nodeList.filter((n) => (live.containers.get(n.uuid) ?? []).length > 0),
);

// Group headers via bifrost.group labels; ungrouped last.
const groups = computed(() => {
  const map = new Map<string, typeof filtered.value>();
  for (const container of filtered.value) {
    const key = container.meta.group ?? '';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(container);
  }
  return [...map.entries()].sort(([a], [b]) =>
    a === '' ? 1 : b === '' ? -1 : a.localeCompare(b),
  );
});

function toggleNode(uuid: string): void {
  nodeFilter.value = nodeFilter.value === uuid ? null : uuid;
}
</script>

<template>
  <section v-if="live.containerList.length > 0" class="services">
    <header class="section-head">
      <h2 class="title">{{ t('services.title') }}</h2>
      <BfChip mono>
        {{ t('services.count', { running: runningCount, total: live.containerList.length }) }}
      </BfChip>
      <span class="filters">
        <button
          v-for="node in nodesWithContainers"
          :key="node.uuid"
          class="filter"
          :class="{ active: nodeFilter === node.uuid }"
          type="button"
          @click="toggleNode(node.uuid)"
        >
          {{ node.name }}
        </button>
      </span>
    </header>

    <div v-for="([group, list], gi) in groups" :key="group || '_'" class="group">
      <h3 v-if="group" class="group-title">{{ group }}</h3>
      <div class="grid bf-stagger">
        <ContainerCard
          v-for="(container, i) in list"
          :key="container.node_uuid + container.id"
          :container="container"
          :style="{ '--i': gi + i }"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.services {
  margin-top: 2rem;
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
.filter {
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
