/** Deterministic force layout (Fruchterman–Reingold) for the tailnet map.
 *
 * No randomness anywhere: nodes seed on a phyllotaxis spiral over the sorted
 * id list, coincident nodes get an index-based nudge, and the iteration count
 * is fixed — the same tailnet always renders the same constellation, and
 * tests can assert exact positions. Pinned nodes (the internet gate) keep
 * their spot; everything else settles around them. */

import type { TailnetEdge } from '@/api/tailnet';

export interface XY {
  x: number;
  y: number;
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const ITERATIONS = 260;
const PAD = 64;

export function computeLayout(
  ids: readonly string[],
  links: ReadonlyArray<readonly [string, string]>,
  width: number,
  height: number,
  pinned: Readonly<Record<string, XY>> = {},
): Map<string, XY> {
  const order = [...ids].sort();
  const n = order.length;
  const out = new Map<string, XY>();
  if (n === 0) return out;

  const cx = width / 2;
  const cy = height / 2;
  const maxR = Math.min(width, height) * 0.38;
  const xs = new Float64Array(n);
  const ys = new Float64Array(n);
  const index = new Map<string, number>();
  order.forEach((id, i) => {
    index.set(id, i);
    const pin = pinned[id];
    const r = maxR * Math.sqrt((i + 0.5) / n);
    xs[i] = pin ? pin.x : cx + r * Math.cos(i * GOLDEN_ANGLE);
    ys[i] = pin ? pin.y : cy + r * Math.sin(i * GOLDEN_ANGLE);
  });

  // Undirected springs, deduplicated — A⇄B must not pull twice as hard.
  const springs: Array<[number, number]> = [];
  const seen = new Set<string>();
  for (const [a, b] of links) {
    const i = index.get(a);
    const j = index.get(b);
    if (i === undefined || j === undefined || i === j) continue;
    const key = i < j ? `${i}:${j}` : `${j}:${i}`;
    if (!seen.has(key)) {
      seen.add(key);
      springs.push([i, j]);
    }
  }

  const k = 0.9 * Math.sqrt((width * height) / n);
  const maxT = Math.max(width, height) * 0.1;
  const dx = new Float64Array(n);
  const dy = new Float64Array(n);
  for (let iter = 0; iter < ITERATIONS; iter++) {
    dx.fill(0);
    dy.fill(0);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let vx = xs[i] - xs[j];
        let vy = ys[i] - ys[j];
        let d2 = vx * vx + vy * vy;
        if (d2 < 1e-4) {
          vx = 0.011 * (i - j);
          vy = 0.017 * (i + 1);
          d2 = vx * vx + vy * vy;
        }
        const f = (k * k) / d2;
        dx[i] += vx * f;
        dy[i] += vy * f;
        dx[j] -= vx * f;
        dy[j] -= vy * f;
      }
    }
    for (const [i, j] of springs) {
      const vx = xs[i] - xs[j];
      const vy = ys[i] - ys[j];
      const pull = Math.hypot(vx, vy) / k;
      dx[i] -= vx * pull;
      dy[i] -= vy * pull;
      dx[j] += vx * pull;
      dy[j] += vy * pull;
    }
    const t = 1 + maxT * (1 - iter / ITERATIONS);
    for (let i = 0; i < n; i++) {
      if (pinned[order[i]]) continue;
      // Light gravity keeps policy-isolated nodes from drifting to the rim.
      dx[i] += (cx - xs[i]) * 0.04;
      dy[i] += (cy - ys[i]) * 0.04;
      const len = Math.hypot(dx[i], dy[i]) || 1;
      const cap = Math.min(len, t);
      xs[i] = Math.min(width - PAD, Math.max(PAD, xs[i] + (dx[i] / len) * cap));
      ys[i] = Math.min(height - PAD, Math.max(PAD, ys[i] + (dy[i] / len) * cap));
    }
  }

  order.forEach((id, i) => {
    out.set(id, { x: Math.round(xs[i] * 100) / 100, y: Math.round(ys[i] * 100) / 100 });
  });
  return out;
}

export interface PairEdge {
  a: string;
  b: string;
  /** a → b ports; null when that direction is not allowed. */
  ab: string[] | null;
  /** b → a ports; null when that direction is not allowed. */
  ba: string[] | null;
}

/** Directed edges → one drawable link per unordered pair (a < b). */
export function mergeEdges(edges: readonly TailnetEdge[]): PairEdge[] {
  const pairs = new Map<string, PairEdge>();
  for (const edge of edges) {
    const flip = edge.dst < edge.src;
    const a = flip ? edge.dst : edge.src;
    const b = flip ? edge.src : edge.dst;
    const key = `${a}|${b}`;
    let pair = pairs.get(key);
    if (!pair) {
      pair = { a, b, ab: null, ba: null };
      pairs.set(key, pair);
    }
    if (flip) pair.ba = edge.ports;
    else pair.ab = edge.ports;
  }
  return [...pairs.values()];
}
