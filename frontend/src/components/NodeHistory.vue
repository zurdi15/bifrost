<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { api } from '@/api/client';
import BfCard from '@/lib/structural/BfCard.vue';
import BfTimeSeries, { type TimeSeriesData } from '@/lib/charts/BfTimeSeries.vue';

const props = defineProps<{ uuid: string; interfaces: string[] }>();

const { t } = useI18n();

const RANGES = [
  { key: '1h', seconds: 3600 },
  { key: '6h', seconds: 6 * 3600 },
  { key: '24h', seconds: 24 * 3600 },
  { key: '7d', seconds: 7 * 86400 },
] as const;

const range = ref<(typeof RANGES)[number]>(RANGES[2]);
const loading = ref(false);
const panels = ref<{ title: string; data: TimeSeriesData }[]>([]);

interface PanelSpec {
  title: string;
  series: { metric: string; label: string; color: string }[];
}

const specs = computed<PanelSpec[]>(() => [
  {
    title: `${t('metric.cpu')} %`,
    series: [{ metric: 'cpu.pct', label: 'cpu', color: 'var(--bf-metric-cpu)' }],
  },
  {
    title: `${t('metric.mem')} %`,
    series: [{ metric: 'mem.pct', label: 'mem', color: 'var(--bf-metric-mem)' }],
  },
  {
    title: `${t('metric.temp')} °C`,
    series: [{ metric: 'temp.cpu', label: 'temp', color: 'var(--bf-metric-temp)' }],
  },
  {
    title: t('metric.load'),
    series: [{ metric: 'cpu.load1', label: 'load1', color: 'var(--bf-metric-cpu)' }],
  },
  ...props.interfaces.map((iface) => ({
    title: `${t('metric.net')} · ${iface} (B/s)`,
    series: [
      { metric: `net.${iface}.rx_bps`, label: 'rx', color: 'var(--bf-metric-net-rx)' },
      { metric: `net.${iface}.tx_bps`, label: 'tx', color: 'var(--bf-metric-net-tx)' },
    ],
  })),
]);

async function load(): Promise<void> {
  loading.value = true;
  try {
    const to = Math.floor(Date.now() / 1000);
    const from = to - range.value.seconds;
    const names = specs.value.flatMap((p) => p.series.map((s) => s.metric));
    const response = await api.metrics(props.uuid, names, from, to);
    const aggregated = response.res !== 'raw';

    panels.value = specs.value
      .map((spec) => {
        // Panels share one x axis per panel: union of their series' timestamps.
        const tsSet = new Set<number>();
        for (const s of spec.series) {
          for (const row of response.series[s.metric] ?? []) tsSet.add(row[0]);
        }
        const ts = [...tsSet].sort((a, b) => a - b);
        const index = new Map(ts.map((v, i) => [v, i]));
        const data: TimeSeriesData = {
          ts,
          series: spec.series.map((s) => {
            const values = new Array<number | null>(ts.length).fill(null);
            const min = aggregated ? new Array<number | null>(ts.length).fill(null) : undefined;
            const max = aggregated ? new Array<number | null>(ts.length).fill(null) : undefined;
            for (const row of response.series[s.metric] ?? []) {
              const i = index.get(row[0])!;
              values[i] = row[1];
              if (aggregated && min && max) {
                min[i] = row[2];
                max[i] = row[3];
              }
            }
            return { label: s.label, color: s.color, values, min, max };
          }),
        };
        return { title: spec.title, data };
      })
      .filter((panel) => panel.data.ts.length > 1);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(range, load);
watch(() => props.interfaces.length, load);
</script>

<template>
  <section class="history">
    <header class="head">
      <h2 class="title">{{ t('detail.history') }}</h2>
      <div class="ranges" role="group">
        <button
          v-for="r in RANGES"
          :key="r.key"
          type="button"
          class="range bf-metric"
          :class="{ active: range.key === r.key }"
          @click="range = r"
        >
          {{ r.key }}
        </button>
      </div>
    </header>

    <div class="grid" :class="{ dimmed: loading }">
      <BfCard v-for="panel in panels" :key="panel.title" class="panel">
        <span class="panel-title">{{ panel.title }}</span>
        <BfTimeSeries :data="panel.data" :height="170" />
      </BfCard>
      <p v-if="!loading && panels.length === 0" class="empty">
        {{ t('detail.noHistory') }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.history {
  margin-top: 2rem;
}
.head {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}
.title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--bf-ink-secondary);
}
.ranges {
  display: flex;
  gap: 0.25rem;
  margin-left: auto;
}
.range {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  border-radius: var(--bf-radius-ctl);
  border: 1px solid var(--bf-line);
  background: transparent;
  color: var(--bf-ink-muted);
  cursor: pointer;
  transition:
    color var(--bf-dur-150),
    border-color var(--bf-dur-150),
    background-color var(--bf-dur-150);
}
.range:hover {
  border-color: var(--bf-line-hover);
  color: var(--bf-ink);
}
.range.active {
  color: var(--bf-brand);
  border-color: var(--bf-brand);
  background: var(--bf-brand-tint);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 1rem;
  transition: opacity var(--bf-dur-150);
}
.grid.dimmed {
  opacity: 0.6;
}
.panel-title {
  display: block;
  margin-bottom: 0.6rem;
  font-size: 0.7rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--bf-ink-muted);
}
.empty {
  color: var(--bf-ink-muted);
  font-size: 0.85rem;
}
</style>
