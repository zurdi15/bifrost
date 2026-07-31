<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import EndpointForm from '@/components/EndpointForm.vue';
import NodeCard from '@/components/NodeCard.vue';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfSkeleton from '@/lib/structural/BfSkeleton.vue';
import { useLiveStore } from '@/stores/live';

const { t } = useI18n();
const live = useLiveStore();

const loading = computed(() => live.connection === 'connecting' && live.nodeList.length === 0);
const downCount = computed(() => live.downNodes.length);
</script>

<template>
  <section>
    <header class="section-head">
      <h2 class="title">{{ t('nodes.title') }}</h2>
      <BfChip mono>
        {{ t('nodes.up', { up: live.upCount, total: live.nodeList.length }) }}
      </BfChip>
      <BfChip v-if="downCount > 0" tone="down" mono>
        {{ t('nodes.down', { count: downCount }) }}
      </BfChip>
      <span class="head-actions"><EndpointForm /></span>
    </header>

    <!-- First load only: skeletons with the real card silhouette. -->
    <div v-if="loading" class="grid" aria-busy="true">
      <div v-for="i in 4" :key="i" class="skeleton-card">
        <div class="skeleton-row">
          <BfSkeleton width="10px" height="10px" rounded="pill" />
          <BfSkeleton width="40%" height="0.9rem" />
        </div>
        <BfSkeleton width="60%" height="0.7rem" />
        <BfSkeleton width="100%" height="34px" />
        <div class="skeleton-row">
          <BfSkeleton width="64px" height="64px" rounded="pill" />
          <BfSkeleton width="64px" height="64px" rounded="pill" />
        </div>
      </div>
    </div>

    <p v-else-if="live.nodeList.length === 0" class="empty">
      {{ t('nodes.empty') }}
    </p>

    <div v-else class="grid bf-stagger">
      <RouterLink
        v-for="(node, i) in live.nodeList"
        :key="node.uuid"
        :to="`/nodes/${node.uuid}`"
        class="card-link"
        :style="{ '--i': i }"
      >
        <NodeCard :node="node" />
      </RouterLink>
    </div>
  </section>
</template>

<style scoped>
.section-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0 1.1rem;
  flex-wrap: wrap;
}
.head-actions {
  margin-left: auto;
}
.title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--bf-ink-secondary);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}
.card-link {
  text-decoration: none;
  color: inherit;
  display: block;
  border-radius: var(--bf-radius-card);
}
.skeleton-card {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
  padding: 1rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-card);
  background: var(--bf-surface);
}
.skeleton-row {
  display: flex;
  align-items: center;
  gap: 0.7rem;
}
.empty {
  color: var(--bf-ink-muted);
  padding: 2.5rem 0;
  text-align: center;
}
</style>
