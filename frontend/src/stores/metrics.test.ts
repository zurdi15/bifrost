import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it } from 'vitest';

import { RING_CAPACITY, useMetricsStore } from './metrics';

describe('metrics store', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('ingests and reads back series in order', () => {
    const store = useMetricsStore();
    store.ingest('n1', { 'cpu.pct': 10 });
    store.ingest('n1', { 'cpu.pct': 20 });
    store.ingest('n1', { 'cpu.pct': 30 });
    expect(store.series('n1', 'cpu.pct')).toEqual([10, 20, 30]);
  });

  it('is bounded by the ring capacity', () => {
    const store = useMetricsStore();
    for (let i = 0; i < RING_CAPACITY + 50; i++) {
      store.ingest('n1', { 'cpu.pct': i });
    }
    const series = store.series('n1', 'cpu.pct');
    expect(series).toHaveLength(RING_CAPACITY);
    expect(series[0]).toBe(50); // oldest 50 evicted
    expect(series.at(-1)).toBe(RING_CAPACITY + 49);
  });

  it('keeps nodes and metrics isolated', () => {
    const store = useMetricsStore();
    store.ingest('n1', { 'cpu.pct': 1, 'mem.pct': 2 });
    store.ingest('n2', { 'cpu.pct': 3 });
    expect(store.series('n1', 'cpu.pct')).toEqual([1]);
    expect(store.series('n1', 'mem.pct')).toEqual([2]);
    expect(store.series('n2', 'cpu.pct')).toEqual([3]);
    expect(store.series('n2', 'mem.pct')).toEqual([]);
  });

  it('seed replaces history and trims to capacity', () => {
    const store = useMetricsStore();
    store.ingest('n1', { 'cpu.pct': 999 });
    const points: [number, number][] = Array.from({ length: RING_CAPACITY + 10 }, (_, i) => [
      i,
      i * 2,
    ]);
    store.seed('n1', 'cpu.pct', points);
    const series = store.series('n1', 'cpu.pct');
    expect(series).toHaveLength(RING_CAPACITY);
    expect(series.at(-1)).toBe((RING_CAPACITY + 9) * 2);
  });
});
