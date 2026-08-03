<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
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
import { useLiveStore } from '@/stores/live';
import { useMetricsStore } from '@/stores/metrics';
import { formatBps, formatClock, formatUptime } from '@/utils/format';

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

// ── speedtest: phases, count-up numbers and a local run history ────────────
interface SpeedRun {
  ts: number;
  down: number;
  up: number;
  lat: number;
}
type SpeedPhase = 'idle' | 'latency' | 'download' | 'upload' | 'done';
const speedPhase = ref<SpeedPhase>('idle');
const speedRunning = computed(() =>
  ['latency', 'download', 'upload'].includes(speedPhase.value),
);
const speedProgress = ref(0);
const speedError = ref('');
const lastRunTs = ref<number | null>(null);
const shown = reactive({ down: 0, up: 0, lat: 0 });
const speedHistory = ref<SpeedRun[]>([]);
let speedTimer: number | undefined;

const historyKey = computed(() => `bf-speedtest-${uuid.value}`);

function loadSpeedHistory(): void {
  try {
    speedHistory.value = JSON.parse(localStorage.getItem(historyKey.value) ?? '[]');
  } catch {
    speedHistory.value = [];
  }
  const last = speedHistory.value.at(-1);
  if (last) {
    Object.assign(shown, { down: last.down, up: last.up, lat: last.lat });
    lastRunTs.value = last.ts;
    speedPhase.value = 'done';
  }
}
onMounted(loadSpeedHistory);

function animateNumbers(finals: { down: number; up: number; lat: number }): void {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    Object.assign(shown, finals);
    return;
  }
  const start = performance.now();
  const duration = 900;
  const tick = (now: number) => {
    const t01 = Math.min((now - start) / duration, 1);
    const eased = 1 - (1 - t01) ** 3;
    shown.down = finals.down * eased;
    shown.up = finals.up * eased;
    shown.lat = finals.lat * eased;
    if (t01 < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

async function runSpeedtest(): Promise<void> {
  speedError.value = '';
  speedProgress.value = 0;
  speedPhase.value = 'latency';
  Object.assign(shown, { down: 0, up: 0, lat: 0 });
  const started = performance.now();
  // The agent phases have fixed windows (~2s latency, 8s down, 8s up), so a
  // client-side clock is an honest progress source.
  speedTimer = window.setInterval(() => {
    const elapsed = (performance.now() - started) / 1000;
    speedProgress.value = Math.min(elapsed / 19, 0.97);
    speedPhase.value = elapsed < 2 ? 'latency' : elapsed < 10.5 ? 'download' : 'upload';
  }, 120);
  try {
    const response = await fetch(`/api/v1/nodes/${uuid.value}/speedtest`, { method: 'POST' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    if (result.error) throw new Error(result.error);
    const run: SpeedRun = {
      ts: Math.floor(Date.now() / 1000),
      down: result.download_mbps ?? 0,
      up: result.upload_mbps ?? 0,
      lat: result.latency_ms ?? 0,
    };
    speedHistory.value = [...speedHistory.value, run].slice(-12);
    localStorage.setItem(historyKey.value, JSON.stringify(speedHistory.value));
    lastRunTs.value = run.ts;
    speedProgress.value = 1;
    speedPhase.value = 'done';
    animateNumbers(run);
  } catch {
    speedError.value = t('detail.speedtestFailed');
    speedPhase.value = speedHistory.value.length > 0 ? 'done' : 'idle';
  } finally {
    window.clearInterval(speedTimer);
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
      <span class="bf-tip-bottom" :data-bf-tip="t(`status.${node.status}`)">
        <BfStatusDot :status="node.status" :desync-id="node.uuid" :size="12" />
      </span>
      <h1 class="name">{{ node.name }}</h1>
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

    <BfCard class="speedtest">
      <header class="panel-head">
        <span class="panel-label">{{ t('detail.speedtest') }}</span>
        <span v-if="!speedRunning && lastRunTs" class="speed-when bf-metric">
          {{ formatClock(lastRunTs) }}
        </span>
        <BfButton
          size="sm"
          variant="primary"
          :disabled="speedRunning || node.status !== 'online'"
          @click="runSpeedtest"
        >
          <span v-if="speedRunning" class="speed-live-dot" aria-hidden="true" />
          {{ speedRunning ? t(`detail.speedPhase.${speedPhase}`) : t('detail.speedtest') }}
        </BfButton>
      </header>

      <div v-if="speedRunning" class="speed-track" aria-hidden="true">
        <span class="speed-fill" :style="{ transform: `scaleX(${speedProgress})` }" />
      </div>

      <div class="speed-tiles" :class="{ running: speedRunning }">
        <div class="speed-tile" style="--tile: var(--bf-metric-net-rx)">
          <span class="speed-arrow">↓</span>
          <span class="speed-value bf-metric">{{ shown.down.toFixed(0) }}</span>
          <span class="speed-unit">Mbps</span>
          <span class="speed-name">{{ t('detail.speedDown') }}</span>
          <svg class="speed-wave" viewBox="0 0 120 26" preserveAspectRatio="none" aria-hidden="true">
            <path d="M0 20 C 12 20 14 6 26 6 S 40 22 52 22 66 4 78 8 100 18 120 10" />
          </svg>
        </div>
        <div class="speed-tile" style="--tile: var(--bf-metric-net-tx)">
          <span class="speed-arrow">↑</span>
          <span class="speed-value bf-metric">{{ shown.up.toFixed(0) }}</span>
          <span class="speed-unit">Mbps</span>
          <span class="speed-name">{{ t('detail.speedUp') }}</span>
          <svg class="speed-wave" viewBox="0 0 120 26" preserveAspectRatio="none" aria-hidden="true">
            <path d="M0 12 C 14 24 24 4 38 8 S 60 22 74 16 96 4 120 14" />
          </svg>
        </div>
        <div class="speed-tile" style="--tile: var(--bf-metric-cpu)">
          <span class="speed-arrow">⌀</span>
          <span class="speed-value bf-metric">{{ shown.lat.toFixed(0) }}</span>
          <span class="speed-unit">ms</span>
          <span class="speed-name">{{ t('detail.speedLat') }}</span>
          <svg class="speed-wave" viewBox="0 0 120 26" preserveAspectRatio="none" aria-hidden="true">
            <path d="M0 16 L 18 16 24 6 30 22 36 16 62 16 68 8 74 20 80 16 120 16" />
          </svg>
        </div>
      </div>

      <div v-if="speedHistory.length >= 2" class="speed-history">
        <span class="speed-name">{{ t('detail.speedHistory') }}</span>
        <div class="speed-history-lines">
          <BfSparkline
            :points="speedHistory.map((h) => h.down)"
            :width="260"
            :height="30"
            :min="0"
            color="var(--bf-metric-net-rx)"
            class="panel-spark"
          />
          <BfSparkline
            :points="speedHistory.map((h) => h.up)"
            :width="260"
            :height="30"
            :min="0"
            color="var(--bf-metric-net-tx)"
            class="panel-spark"
          />
        </div>
      </div>

      <BfChip v-if="speedError" tone="down">{{ speedError }}</BfChip>
    </BfCard>

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
.speedtest {
  margin-top: 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.speed-when {
  margin-left: auto;
  margin-right: 0.8rem;
  font-size: 0.72rem;
  color: var(--bf-ink-muted);
}
.speedtest .panel-head .speed-when + * {
  margin-left: 0;
}
.speed-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--bf-status-up);
  display: inline-block;
  margin-right: 0.45rem;
  animation: speed-pulse 1.1s var(--bf-ease-spring) infinite;
}
@keyframes speed-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.35;
    transform: scale(0.65);
  }
}
.speed-track {
  height: 3px;
  border-radius: 2px;
  background: var(--bf-line);
  overflow: hidden;
}
.speed-fill {
  display: block;
  height: 100%;
  transform-origin: left;
  background: var(--bf-aurora);
  background-size: 300% 100%;
  animation: bf-aurora-drift 6s linear infinite;
  transition: transform var(--bf-dur-150) linear;
}
.speed-tiles {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.8rem;
}
.speed-tile {
  position: relative;
  overflow: hidden;
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: baseline;
  column-gap: 0.4rem;
  padding: 0.75rem 0.85rem 1.6rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
}
.speed-arrow {
  color: var(--tile);
  font-weight: 700;
  font-size: 1.05rem;
}
.speed-value {
  font-size: 1.7rem;
  font-weight: 650;
  color: var(--bf-ink-strong);
  line-height: 1;
}
.speed-unit {
  font-size: 0.72rem;
  color: var(--bf-ink-muted);
}
.speed-name {
  grid-column: 1 / -1;
  margin-top: 0.35rem;
  font-size: 0.66rem;
  font-weight: 650;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--bf-ink-muted);
}
.speed-wave {
  position: absolute;
  inset: auto 0 0 0;
  width: 100%;
  height: 22px;
}
.speed-wave path {
  fill: none;
  stroke: var(--tile);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-dasharray: 240;
  stroke-dashoffset: 240;
}
.speed-tiles.running .speed-wave path {
  animation: speed-draw 1.7s var(--bf-ease-spring) infinite;
}
.speed-tiles:not(.running) .speed-wave path {
  stroke-dashoffset: 0;
  opacity: 0.45;
  transition: stroke-dashoffset var(--bf-dur-800) var(--bf-ease-spring);
}
@keyframes speed-draw {
  0% {
    stroke-dashoffset: 240;
    opacity: 1;
  }
  70% {
    stroke-dashoffset: 0;
    opacity: 1;
  }
  100% {
    stroke-dashoffset: 0;
    opacity: 0.15;
  }
}
.speed-history {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.speed-history-lines {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
@media (max-width: 720px) {
  .speed-tiles {
    grid-template-columns: 1fr;
  }
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
