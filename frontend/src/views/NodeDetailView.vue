<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';

import { api } from '@/api/client';
import { mdiArrowLeft, mdiOpenInNew, mdiPencil } from '@mdi/js';
import NodeFilesystems from '@/components/NodeFilesystems.vue';
import NodeHistory from '@/components/NodeHistory.vue';
import BfButton from '@/lib/primitives/BfButton.vue';
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

// Node URL (a NAS dashboard, HAOS…) editable right from the hero.
const editingUrl = ref(false);
const urlDraft = ref('');
const savingUrl = ref(false);

function openUrlEditor(): void {
  urlDraft.value = node.value?.url ?? '';
  editingUrl.value = true;
}

const speedtesting = ref(false);
interface SpeedtestResult {
  latency_ms: number | null;
  download_mbps: number | null;
  upload_mbps: number | null;
  error?: string;
}
const speedtestResult = ref<SpeedtestResult | null>(null);
const speedtestError = ref('');

async function runSpeedtest(): Promise<void> {
  speedtesting.value = true;
  speedtestError.value = '';
  speedtestResult.value = null;
  try {
    const response = await fetch(`/api/v1/nodes/${uuid.value}/speedtest`, { method: 'POST' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = (await response.json()) as SpeedtestResult;
    if (result.error) speedtestError.value = result.error;
    else speedtestResult.value = result;
  } catch {
    speedtestError.value = t('detail.speedtestFailed');
  } finally {
    speedtesting.value = false;
  }
}

async function saveUrl(): Promise<void> {
  savingUrl.value = true;
  try {
    await api.patchNode(uuid.value, { url: urlDraft.value });
    await live.snapshot();
    editingUrl.value = false;
  } finally {
    savingUrl.value = false;
  }
}

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
    <RouterLink to="/nodes" class="back">
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

      <span class="url-zone">
        <template v-if="!editingUrl">
          <a
            v-if="node.url"
            :href="node.url"
            target="_blank"
            rel="noreferrer"
            class="node-url bf-metric"
          >
            {{ node.url }}
            <BfIcon :path="mdiOpenInNew" :size="12" />
          </a>
          <button
            class="url-edit"
            type="button"
            :data-bf-tip="t('detail.setUrl')"
            :aria-label="t('detail.setUrl')"
            @click="openUrlEditor"
          >
            <BfIcon :path="mdiPencil" :size="12" />
          </button>
        </template>
        <form v-else class="url-form" @submit.prevent="saveUrl" @keydown.esc="editingUrl = false">
          <input
            v-model="urlDraft"
            class="url-field bf-metric"
            :placeholder="t('detail.urlPlaceholder')"
          />
          <BfButton size="sm" variant="primary" :disabled="savingUrl">
            {{ t('service.save') }}
          </BfButton>
        </form>
      </span>

      <span class="speed-zone">
        <BfButton size="sm" :disabled="speedtesting || node.status !== 'online'" @click="runSpeedtest">
          {{ speedtesting ? t('detail.speedtestRunning') : t('detail.speedtest') }}
        </BfButton>
        <span v-if="speedtestResult" class="speed-result bf-metric">
          ↓ {{ Math.round(speedtestResult.download_mbps ?? 0) }} Mbps · ↑
          {{ Math.round(speedtestResult.upload_mbps ?? 0) }} Mbps ·
          {{ Math.round(speedtestResult.latency_ms ?? 0) }} ms
        </span>
        <BfChip v-if="speedtestError" tone="down">{{ speedtestError }}</BfChip>
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
.speed-zone {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
}
.speed-result {
  font-size: 0.8rem;
  color: var(--bf-ink-secondary);
}
.url-zone {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-left: auto;
}
.node-url {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.75rem;
  color: var(--bf-ink-secondary);
  text-decoration: none;
}
.node-url:hover {
  color: var(--bf-brand);
}
.url-edit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
  background: var(--bf-surface-raised);
  color: var(--bf-ink-secondary);
  cursor: pointer;
  transition:
    color var(--bf-dur-150),
    border-color var(--bf-dur-150);
}
.url-edit:hover {
  color: var(--bf-ink);
  border-color: var(--bf-line-hover);
}
.url-form {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.url-field {
  font: inherit;
  font-size: 0.78rem;
  min-width: 16rem;
  padding: 0.3rem 0.55rem;
  background: var(--bf-surface-sunken);
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
  color: var(--bf-ink);
  transition: border-color var(--bf-dur-150);
}
.url-field:focus {
  border-color: var(--bf-brand);
  outline: none;
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
