import { defineStore } from 'pinia';
import { reactive } from 'vue';

/** Points kept per node+metric — enough for an hour of 10s samples without
 * ever growing memory. */
export const RING_CAPACITY = 360;

class Ring {
  private readonly values = new Float64Array(RING_CAPACITY);
  private head = 0;
  private count = 0;

  push(value: number): void {
    this.values[this.head] = value;
    this.head = (this.head + 1) % RING_CAPACITY;
    if (this.count < RING_CAPACITY) this.count += 1;
  }

  toArray(): number[] {
    const out = new Array<number>(this.count);
    const start = (this.head - this.count + RING_CAPACITY) % RING_CAPACITY;
    for (let i = 0; i < this.count; i++) {
      out[i] = this.values[(start + i) % RING_CAPACITY];
    }
    return out;
  }

  get size(): number {
    return this.count;
  }
}

export const useMetricsStore = defineStore('metrics', () => {
  // Rings are non-reactive by design (Float64Array churn); `versions` is the
  // reactive tick sparklines watch to re-read their ring.
  const rings = new Map<string, Ring>();
  const versions = reactive(new Map<string, number>());

  function key(nodeUuid: string, metric: string): string {
    return `${nodeUuid}:${metric}`;
  }

  function ingest(nodeUuid: string, samples: Record<string, number>): void {
    for (const [metric, value] of Object.entries(samples)) {
      const k = key(nodeUuid, metric);
      let ring = rings.get(k);
      if (!ring) {
        ring = new Ring();
        rings.set(k, ring);
      }
      ring.push(value);
      versions.set(k, (versions.get(k) ?? 0) + 1);
    }
  }

  /** Seed a ring from a REST history query (node detail view).
   * Rows are [ts, value] (raw) or [ts, avg, min, max] (aggregated). */
  function seed(nodeUuid: string, metric: string, points: number[][]): void {
    const k = key(nodeUuid, metric);
    const ring = new Ring();
    for (const row of points.slice(-RING_CAPACITY)) ring.push(row[1]);
    rings.set(k, ring);
    versions.set(k, (versions.get(k) ?? 0) + 1);
  }

  function series(nodeUuid: string, metric: string): number[] {
    // Touch the version so callers re-run when the ring advances.
    versions.get(key(nodeUuid, metric));
    return rings.get(key(nodeUuid, metric))?.toArray() ?? [];
  }

  function clear(): void {
    rings.clear();
    versions.clear();
  }

  return { ingest, seed, series, clear };
});
