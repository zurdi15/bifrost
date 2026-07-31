<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import type { DiskInfo } from '@/api/types';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import NodeFilesystems from '@/components/NodeFilesystems.vue';
import { useLiveStore } from '@/stores/live';
import { formatBytes } from '@/utils/format';

const { t } = useI18n();
const live = useLiveStore();

// Every agent node belongs here: SMART disks when reported, filesystems
// always. Filtering by disks alone made SD-card/no-SMART nodes vanish.
const nodesWithStorage = computed(() =>
  live.nodeList.filter(
    (n) => n.kind === 'agent' || (live.disks.get(n.uuid) ?? []).length > 0,
  ),
);
const totalDisks = computed(
  () => [...live.disks.values()].reduce((acc, list) => acc + list.length, 0),
);
const healthyDisks = computed(
  () =>
    [...live.disks.values()]
      .flat()
      .filter((d) => d.smart_status === 'passed').length,
);

function smartTone(disk: DiskInfo): 'up' | 'down' | 'degraded' | 'unknown' {
  if (disk.smart_status === 'passed') {
    const preFail = (disk.realloc_sectors ?? 0) > 0 || (disk.pending_sectors ?? 0) > 0;
    return preFail ? 'degraded' : 'up';
  }
  if (disk.smart_status === 'failed') return 'down';
  return 'unknown';
}

function smartLabel(disk: DiskInfo): string {
  if (disk.smart_status === 'passed' && smartTone(disk) === 'degraded') {
    return t('storage.prefail');
  }
  return disk.smart_status ?? 'unknown';
}
</script>

<template>
  <section>
    <header class="section-head">
      <h2 class="title">{{ t('storage.title') }}</h2>
      <BfChip mono>{{ t('storage.count', { ok: healthyDisks, total: totalDisks }) }}</BfChip>
    </header>

    <p v-if="nodesWithStorage.length === 0" class="empty">{{ t('storage.empty') }}</p>

    <div class="nodes bf-stagger">
      <BfCard
        v-for="(node, i) in nodesWithStorage"
        :key="node.uuid"
        class="node-block"
        :style="{ '--i': i }"
      >
        <h3 class="node-name">{{ node.name }}</h3>
        <p v-if="(live.disks.get(node.uuid) ?? []).length === 0" class="no-smart">
          {{ t('storage.noSmart') }}
        </p>
        <details v-for="disk in live.disks.get(node.uuid)" :key="disk.serial" class="disk">
          <summary class="disk-row">
            <span class="device bf-metric">{{ disk.device }}</span>
            <span class="model">{{ disk.model }}</span>
            <BfChip v-if="disk.kind" tone="neutral">{{ disk.kind }}</BfChip>
            <span class="spacer" />
            <span v-if="disk.temp_c !== null" class="temp bf-metric">
              {{ disk.temp_c.toFixed(0) }}°
            </span>
            <span v-if="disk.capacity_bytes" class="cap bf-metric">
              {{ formatBytes(disk.capacity_bytes, 0) }}
            </span>
            <BfChip :tone="smartTone(disk)" mono>{{ smartLabel(disk) }}</BfChip>
          </summary>
          <dl class="attrs bf-metric">
            <div><dt>serial</dt><dd>{{ disk.serial }}</dd></div>
            <div v-if="disk.power_on_hours !== null">
              <dt>{{ t('storage.powerOn') }}</dt>
              <dd>{{ Math.floor((disk.power_on_hours ?? 0) / 24) }}d</dd>
            </div>
            <div v-if="disk.realloc_sectors !== null">
              <dt>realloc</dt><dd>{{ disk.realloc_sectors }}</dd>
            </div>
            <div v-if="disk.pending_sectors !== null">
              <dt>pending</dt><dd>{{ disk.pending_sectors }}</dd>
            </div>
            <div v-if="disk.wear_pct !== null">
              <dt>{{ t('storage.wear') }}</dt><dd>{{ disk.wear_pct }}%</dd>
            </div>
          </dl>
        </details>

        <NodeFilesystems :uuid="node.uuid" class="fs" />
      </BfCard>
    </div>
  </section>
</template>

<style scoped>
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
.empty {
  color: var(--bf-ink-muted);
  padding: 2.5rem 0;
  text-align: center;
}
.no-smart {
  margin: 0;
  font-size: 0.78rem;
  color: var(--bf-ink-faint);
}
.nodes {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.node-name {
  margin: 0 0 0.6rem;
  font-size: 1rem;
  font-weight: 650;
  color: var(--bf-ink-strong);
}
.disk + .disk {
  border-top: 1px solid var(--bf-line);
}
.disk-row {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding: 0.55rem 0;
  cursor: pointer;
  list-style: none;
  flex-wrap: wrap;
}
.disk-row::-webkit-details-marker {
  display: none;
}
.device {
  font-size: 0.82rem;
  color: var(--bf-ink-strong);
  font-weight: 600;
}
.model {
  font-size: 0.8rem;
  color: var(--bf-ink-secondary);
}
.spacer {
  flex: 1;
}
.temp,
.cap {
  font-size: 0.78rem;
  color: var(--bf-ink-secondary);
}
.attrs {
  display: flex;
  gap: 1.6rem;
  flex-wrap: wrap;
  margin: 0.2rem 0 0.7rem;
  padding: 0.6rem 0.8rem;
  background: var(--bf-surface-sunken);
  border-radius: var(--bf-radius-ctl);
  font-size: 0.72rem;
  animation: bf-rise-in var(--bf-dur-300) var(--bf-ease-spring) both;
}
.attrs dt {
  color: var(--bf-ink-faint);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 0.6rem;
}
.attrs dd {
  margin: 0.1rem 0 0;
  color: var(--bf-ink);
}
.fs {
  margin-top: 1rem;
}
</style>
