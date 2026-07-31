<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';

import { api } from '@/api/client';
import { mdiArrowLeft } from '@mdi/js';
import NodeFilesystems from '@/components/NodeFilesystems.vue';
import NodeHistory from '@/components/NodeHistory.vue';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import BfGauge from '@/lib/data/BfGauge.vue';
import BfSparkline from '@/lib/data/BfSparkline.vue';
import BfStatusDot from '@/lib/data/BfStatusDot.vue';
import { statusToken } from '@/tokens';
import { useLiveStore } from '@/stores/live';
import { useMetricsStore } from '@/stores/metrics';
import { formatBps, formatUptime } from '@/utils/format';

const route = useRoute();
const { t } = useI18n();
const live = useLiveStore();
const metrics = useMetricsStore();

const uuid = computed(() => String(route.params.uuid));
const node = computed(() => live.nodes.get(uuid.value) ?? null);
const isDown = computed(
  () => node.value?.status === 'offline' || node.value?.status === 'degraded',
);

const cpu = computed(() => node.value?.live?.samples['cpu.pct'] ?? null);
const mem = computed(() => node.value?.live?.samples['mem.pct'] ?? null);
const temp = computed(() => node.value?.live?.samples['temp.cpu'] ?? null);
const load1 = computed(() => node.value?.live?.samples['cpu.load1'] ?? null);

// Interfaces discovered from the live sample names (net.<if>.rx_bps).
const interfaces = computed(() => {
  const names = Object.keys(node.value?.live?.samples ?? {});
  return [...new Set(
    names
      .filter((n) => n.startsWith('net.') && n.endsWith('.rx_bps'))
      .map((n) => n.slice(4, -7)),
  )].sort();
});

const panels = computed(() => [
  { metric: 'cpu.pct', label: t('metric.cpu'), color: 'var(--bf-metric-cpu)', max: 100 },
  { metric: 'mem.pct', label: t('metric.mem'), color: 'var(--bf-metric-mem)', max: 100 },
  { metric: 'temp.cpu', label: t('metric.temp'), color: 'var(--bf-metric-temp)', max: undefined },
]);

// Seed sparkline rings with the last hour so history shows immediately;
// live WS frames keep appending afterwards.
onMounted(async () => {
  const from = Math.floor(Date.now() / 1000) - 3600;
  const names = ['cpu.pct', 'mem.pct', 'temp.cpu'];
  try {
    const history = await api.metrics(uuid.value, names, from);
    for (const name of names) {
      const points = history.series[name] ?? [];
      if (points.length > 1) metrics.seed(uuid.value, name, points);
    }
  } catch {
    /* node may be brand new — live data will fill in */
  }
});
</script>

<template>
  <section v-if="node">
    <RouterLink to="/" class="back">
      <BfIcon :path="mdiArrowLeft" :size="15" />
      {{ t('detail.back') }}
    </RouterLink>

    <header class="hero" :style="{ viewTransitionName: `node-${node.uuid}` }">
      <BfStatusDot :status="node.status" :desync-id="node.uuid" :size="12" />
      <h1 class="name">{{ node.name }}</h1>
      <BfChip :tone="(statusToken[node.status] as any) ?? 'unknown'" mono>
        {{ t(`status.${node.status}`) }}
      </BfChip>
      <span class="meta bf-metric">
        <template v-if="node.os">{{ node.os }} · </template>
        <template v-if="node.arch">{{ node.arch }} · </template>
        ↑ {{ formatUptime(node.boot_ts) }}
      </span>
    </header>

    <div class="panels bf-stagger">
      <BfCard
        v-for="(panel, i) in panels"
        :key="panel.metric"
        class="panel"
        :style="{ '--i': i }"
      >
        <header class="panel-head">
          <span class="panel-label">{{ panel.label }}</span>
        </header>
        <div class="panel-body">
          <BfGauge
            v-if="panel.metric === 'cpu.pct' && cpu !== null"
            :value="cpu"
            :size="92"
            :color="panel.color"
          />
          <BfGauge
            v-else-if="panel.metric === 'mem.pct' && mem !== null"
            :value="mem"
            :size="92"
            :color="panel.color"
          />
          <BfGauge
            v-else-if="panel.metric === 'temp.cpu' && temp !== null"
            :value="temp"
            unit="°"
            :size="92"
            :color="panel.color"
            :warn-at="70"
            :danger-at="85"
          />
          <BfSparkline
            :points="metrics.series(node.uuid, panel.metric)"
            :width="260"
            :height="64"
            :min="panel.max ? 0 : undefined"
            :max="panel.max"
            :color="panel.color"
            :flatline="isDown"
            class="panel-spark"
          />
        </div>
      </BfCard>

      <BfCard v-if="load1 !== null" class="panel" :style="{ '--i': panels.length }">
        <header class="panel-head">
          <span class="panel-label">{{ t('metric.load') }}</span>
        </header>
        <div class="panel-body">
          <span class="big bf-metric">{{ load1.toFixed(2) }}</span>
          <BfSparkline
            :points="metrics.series(node.uuid, 'cpu.load1')"
            :width="260"
            :height="64"
            color="var(--bf-metric-cpu)"
            :flatline="isDown"
            class="panel-spark"
          />
        </div>
      </BfCard>

      <BfCard
        v-for="(iface, i) in interfaces"
        :key="iface"
        class="panel"
        :style="{ '--i': panels.length + 1 + i }"
      >
        <header class="panel-head">
          <span class="panel-label">{{ t('metric.net') }} · {{ iface }}</span>
          <span class="net-now bf-metric">
            ↓ {{ formatBps(node.live?.samples[`net.${iface}.rx_bps`] ?? 0) }}
            ↑ {{ formatBps(node.live?.samples[`net.${iface}.tx_bps`] ?? 0) }}
          </span>
        </header>
        <div class="net-sparks">
          <BfSparkline
            :points="metrics.series(node.uuid, `net.${iface}.rx_bps`)"
            :width="260"
            :height="36"
            color="var(--bf-metric-net-rx)"
            :flatline="isDown"
            class="panel-spark"
          />
          <BfSparkline
            :points="metrics.series(node.uuid, `net.${iface}.tx_bps`)"
            :width="260"
            :height="36"
            color="var(--bf-metric-net-tx)"
            :flatline="isDown"
            class="panel-spark"
          />
        </div>
      </BfCard>
    </div>

    <NodeFilesystems :uuid="node.uuid" />
    <NodeHistory :uuid="node.uuid" :interfaces="interfaces" />
  </section>

  <p v-else class="missing">{{ t('detail.notFound') }}</p>
</template>

<style scoped>
.back {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--bf-ink-muted);
  text-decoration: none;
  font-size: 0.8rem;
  margin: 0.75rem 0;
  transition: color var(--bf-dur-150);
}
.back:hover {
  color: var(--bf-ink);
}
.hero {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 0.6rem 0 1.2rem;
  flex-wrap: wrap;
}
.name {
  margin: 0;
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--bf-ink-strong);
}
.meta {
  color: var(--bf-ink-muted);
  font-size: 0.8rem;
}
.panels {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}
.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.7rem;
}
.panel-label {
  font-size: 0.7rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--bf-ink-muted);
}
.panel-body {
  display: flex;
  align-items: center;
  gap: 1rem;
}
.panel-spark {
  flex: 1;
  min-width: 0;
  width: 100%;
}
.net-sparks {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.net-now {
  font-size: 0.72rem;
  color: var(--bf-ink-secondary);
}
.big {
  font-size: 1.7rem;
  font-weight: 600;
  color: var(--bf-ink-strong);
}
.missing {
  color: var(--bf-ink-muted);
  text-align: center;
  padding: 3rem 0;
}
</style>
