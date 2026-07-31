<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { NodeInfo } from '@/api/types';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import BfGauge from '@/lib/data/BfGauge.vue';
import BfNumberRoll from '@/lib/data/BfNumberRoll.vue';
import BfSparkline from '@/lib/data/BfSparkline.vue';
import BfStatusDot from '@/lib/data/BfStatusDot.vue';
import BfSweep from '@/lib/data/BfSweep.vue';
import { useMetricsStore } from '@/stores/metrics';
import { formatClock, formatUptime } from '@/utils/format';

const props = defineProps<{ node: NodeInfo }>();

const { t } = useI18n();
const metrics = useMetricsStore();

const isDown = computed(
  () => props.node.status === 'offline' || props.node.status === 'degraded',
);
const cpu = computed(() => props.node.live?.samples['cpu.pct'] ?? null);
const mem = computed(() => props.node.live?.samples['mem.pct'] ?? null);
const temp = computed(() => props.node.live?.samples['temp.cpu'] ?? null);
const cpuSeries = computed(() => metrics.series(props.node.uuid, 'cpu.pct'));

// One-shot perimeter sweeps on status transitions.
const sweep = ref<'down' | 'aurora' | null>(null);
let sweepTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => props.node.status,
  (next, prev) => {
    if (!prev) return;
    const wasDown = prev === 'offline' || prev === 'degraded';
    if (next === 'offline') sweep.value = 'down';
    else if (next === 'online' && wasDown) sweep.value = 'aurora';
    else return;
    if (sweepTimer) clearTimeout(sweepTimer);
    sweepTimer = setTimeout(() => (sweep.value = null), 1000);
  },
);
</script>

<template>
  <BfCard
    interactive
    class="node-card"
    :class="{ 'is-down': isDown }"
    :style="{ viewTransitionName: `node-${node.uuid}` }"
  >
    <BfSweep :tone="sweep ?? 'down'" :active="sweep !== null" />

    <header class="head">
      <BfStatusDot :status="node.status" :desync-id="node.uuid" />
      <span class="name">{{ node.name }}</span>
      <BfChip v-if="isDown" tone="down" mono class="bf-pop-in">
        {{ t(`status.${node.status}`) }}
      </BfChip>
    </header>

    <p class="meta">
      <span v-if="node.os">{{ node.os }}</span>
      <span v-if="node.arch">· {{ node.arch }}</span>
    </p>

    <div class="spark">
      <BfSparkline
        :points="cpuSeries"
        :width="200"
        :height="34"
        :min="0"
        :max="100"
        color="var(--bf-metric-cpu)"
        :flatline="isDown"
      />
    </div>

    <div class="dim">
      <div class="gauges">
        <BfGauge
          v-if="cpu !== null"
          :value="cpu"
          :size="64"
          label="cpu"
          color="var(--bf-metric-cpu)"
        />
        <BfGauge
          v-if="mem !== null"
          :value="mem"
          :size="64"
          label="mem"
          color="var(--bf-metric-mem)"
        />
        <div class="stats">
          <p v-if="temp !== null" class="stat">
            <BfNumberRoll :value="temp" :decimals="0" suffix="°" />
            <span class="stat-label">{{ t('metric.temp') }}</span>
          </p>
          <p class="stat">
            <span class="bf-metric up">{{ formatUptime(node.boot_ts) }}</span>
            <span class="stat-label">{{ t('nodes.uptime') }}</span>
          </p>
        </div>
      </div>

      <p v-if="isDown && node.last_seen" class="last-seen bf-metric">
        {{ t('nodes.lastSeen') }} {{ formatClock(node.last_seen) }}
      </p>
    </div>
  </BfCard>
</template>

<style scoped>
.node-card {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.is-down {
  border-color: color-mix(in srgb, var(--bf-status-down) 40%, transparent);
}
.head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.name {
  font-weight: 600;
  font-size: 1rem;
  color: var(--bf-ink-strong);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  margin: 0;
  font-size: 0.75rem;
  color: var(--bf-ink-muted);
  display: flex;
  gap: 0.35em;
}
.spark {
  overflow: hidden;
}
/* Down: content dims but the header stays legible. */
.dim {
  transition: opacity var(--bf-dur-500);
}
.is-down .dim {
  opacity: 0.6;
}
.gauges {
  display: flex;
  align-items: center;
  gap: 0.9rem;
}
.stats {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-left: auto;
}
.stat {
  margin: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.1rem;
  font-size: 0.95rem;
  color: var(--bf-ink);
}
.stat .up {
  font-size: 0.85rem;
}
.stat-label {
  font-size: 0.62rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--bf-ink-faint);
}
.last-seen {
  margin: 0;
  font-size: 0.75rem;
  color: var(--bf-status-down);
}
</style>
