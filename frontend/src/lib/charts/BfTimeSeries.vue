<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';

export interface TimeSeriesData {
  ts: number[];
  /** Aligned with ts. Aggregated resolutions may add min/max bands. */
  series: {
    label: string;
    color: string; // resolved CSS color or var(--bf-*)
    values: (number | null)[];
    min?: (number | null)[];
    max?: (number | null)[];
  }[];
}

const props = withDefaults(
  defineProps<{
    data: TimeSeriesData;
    height?: number;
    unit?: string;
  }>(),
  { height: 180, unit: '' },
);

const container = ref<HTMLElement | null>(null);
const chart = shallowRef<uPlot | null>(null);
let resizeObserver: ResizeObserver | null = null;

function cssColor(value: string): string {
  // Resolve var(--bf-*) against the live theme for canvas drawing.
  const match = /^var\((--[\w-]+)\)$/.exec(value.trim());
  if (!match) return value;
  return getComputedStyle(document.documentElement).getPropertyValue(match[1]).trim() || value;
}

function themeToken(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function alignedData(): uPlot.AlignedData {
  const arrays: (number | null)[][] = [];
  for (const s of props.data.series) {
    arrays.push(s.values);
    if (s.min && s.max) {
      arrays.push(s.max, s.min);
    }
  }
  return [props.data.ts, ...arrays] as uPlot.AlignedData;
}

function buildOptions(width: number): uPlot.Options {
  const ink = themeToken('--bf-ink-muted');
  const grid = themeToken('--bf-chart-grid');
  const series: uPlot.Series[] = [{}];
  const bands: uPlot.Band[] = [];
  let idx = 1;
  for (const s of props.data.series) {
    const color = cssColor(s.color);
    series.push({ label: s.label, stroke: color, width: 1.6, points: { show: false } });
    idx += 1;
    if (s.min && s.max) {
      // avg at idx-1, max at idx, min at idx+1 → translucent band between.
      series.push(
        { label: `${s.label} max`, stroke: 'transparent', points: { show: false } },
        { label: `${s.label} min`, stroke: 'transparent', points: { show: false } },
      );
      bands.push({ series: [idx, idx + 1], fill: color + '22' });
      idx += 2;
    }
  }
  return {
    width,
    height: props.height,
    series,
    bands,
    legend: { show: props.data.series.length > 1 },
    cursor: { drag: { x: true, y: false } },
    scales: { x: { time: true } },
    axes: [
      {
        stroke: ink,
        grid: { stroke: grid, width: 1 },
        ticks: { stroke: grid },
        font: '11px JetBrains Mono Variable',
      },
      {
        stroke: ink,
        grid: { stroke: grid, width: 1 },
        ticks: { stroke: grid },
        font: '11px JetBrains Mono Variable',
        size: 52,
      },
    ],
  };
}

function rebuild(): void {
  if (!container.value) return;
  chart.value?.destroy();
  const width = container.value.clientWidth || 300;
  chart.value = new uPlot(buildOptions(width), alignedData(), container.value);
}

onMounted(() => {
  rebuild();
  resizeObserver = new ResizeObserver(() => {
    if (chart.value && container.value) {
      chart.value.setSize({ width: container.value.clientWidth, height: props.height });
    }
  });
  if (container.value) resizeObserver.observe(container.value);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  chart.value?.destroy();
});

watch(
  () => props.data,
  (next, prev) => {
    // Series shape changed → rebuild; same shape → cheap data swap.
    if (!chart.value || next.series.length !== prev?.series.length) rebuild();
    else chart.value.setData(alignedData());
  },
  { deep: true },
);
</script>

<template>
  <div ref="container" class="bf-timeseries" />
</template>

<style scoped>
.bf-timeseries {
  width: 100%;
  min-width: 0;
}
.bf-timeseries :deep(.u-legend) {
  font: 11px var(--bf-font-mono);
  color: var(--bf-ink-muted);
  text-align: left;
}
.bf-timeseries :deep(.u-select) {
  background: var(--bf-brand-tint);
}
</style>
