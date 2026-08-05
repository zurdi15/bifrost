/** Tailnet constellation physics.
 *
 * A little force simulation (repulsion + edge springs + centering gravity +
 * collision floor) that both settles the initial layout and keeps running
 * for interaction: nodes are draggable, neighbors react, everything relaxes
 * back. No randomness anywhere — new nodes seed on a phyllotaxis spiral over
 * the sorted id list and every step is pure arithmetic, so the same tailnet
 * always renders the same constellation and tests can assert positions. */

import type { TailnetEdge } from '@/api/tailnet';

export interface XY {
  x: number;
  y: number;
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const PAD = 64;
// Generous floor: node labels render at ~10px mono below each core, so
// neighbors need real air for names to stay legible (phones especially).
const MIN_DIST = 62;
const FRICTION = 0.58;
const ALPHA_DECAY = 0.968;
const ALPHA_REST = 0.015;
// Below ~half temperature, nodes whose forces roughly balance stay put —
// settling from cold never twitches the far field.
const FORCE_DEADZONE = 0.9;
const SLEEP_SPEED = 0.06;
// Under this temperature the sim is "interactive": drags and releases move
// ONLY the touched node (edges stretch, bystanders hold still) and the
// collision floor shoves someone aside only if you actually drop onto them.
// Full physics still runs for layouts, graph changes and resizes.
const INTERACTIVE_ALPHA = 0.12;

export interface SimNode extends XY {
  id: string;
  vx: number;
  vy: number;
  /** Pointer pin while dragging (or a permanent pin like the internet gate). */
  fx: number | null;
  fy: number | null;
}

export interface Simulation {
  readonly nodes: Map<string, SimNode>;
  setGraph(
    ids: readonly string[],
    links: ReadonlyArray<readonly [string, string]>,
    pinned?: Readonly<Record<string, XY>>,
  ): void;
  resize(width: number, height: number, pinned?: Readonly<Record<string, XY>>): void;
  /** One tick; returns true while the system is still hot. */
  step(): boolean;
  /** Run synchronously until rest (bounded), e.g. for the initial layout. */
  settle(maxSteps?: number): void;
  reheat(alpha?: number): void;
  drag(id: string, x: number, y: number): void;
  release(id: string): void;
  positions(): Map<string, XY>;
}

export function createSimulation(width: number, height: number): Simulation {
  const nodes = new Map<string, SimNode>();
  let springs: Array<[SimNode, SimNode]> = [];
  let w = width;
  let h = height;
  let alpha = 0;

  function seed(id: string, index: number, count: number): SimNode {
    const r = Math.min(w, h) * 0.38 * Math.sqrt((index + 0.5) / Math.max(count, 1));
    return {
      id,
      x: w / 2 + r * Math.cos(index * GOLDEN_ANGLE),
      y: h / 2 + r * Math.sin(index * GOLDEN_ANGLE),
      vx: 0,
      vy: 0,
      fx: null,
      fy: null,
    };
  }

  function setGraph(
    ids: readonly string[],
    links: ReadonlyArray<readonly [string, string]>,
    pinned: Readonly<Record<string, XY>> = {},
  ): void {
    const order = [...ids].sort();
    const keep = new Set(order);
    for (const id of [...nodes.keys()]) {
      if (!keep.has(id)) nodes.delete(id);
    }
    order.forEach((id, index) => {
      let node = nodes.get(id);
      if (!node) {
        node = seed(id, index, order.length);
        nodes.set(id, node);
      }
      const pin = pinned[id];
      node.fx = pin ? pin.x : null;
      node.fy = pin ? pin.y : null;
      if (pin) {
        node.x = pin.x;
        node.y = pin.y;
      }
    });
    springs = [];
    const seen = new Set<string>();
    for (const [a, b] of links) {
      const na = nodes.get(a);
      const nb = nodes.get(b);
      if (!na || !nb || na === nb) continue;
      const key = a < b ? `${a}|${b}` : `${b}|${a}`;
      if (!seen.has(key)) {
        seen.add(key);
        springs.push([na, nb]);
      }
    }
    alpha = 1;
  }

  function resize(
    width2: number,
    height2: number,
    pinned: Readonly<Record<string, XY>> = {},
  ): void {
    if (width2 <= 0 || height2 <= 0) return;
    const sx = width2 / w;
    const sy = height2 / h;
    // Minor changes (a widget popping into the topbar, a scrollbar) must not
    // visibly nudge the constellation — keep positions, just update bounds.
    const minor = sx > 0.97 && sx < 1.03 && sy > 0.97 && sy < 1.03;
    w = width2;
    h = height2;
    for (const node of nodes.values()) {
      if (!minor) {
        node.x *= sx;
        node.y *= sy;
        if (node.fx !== null && node.fy !== null) {
          node.fx *= sx;
          node.fy *= sy;
        }
      }
      const pin = pinned[node.id];
      if (pin) {
        node.fx = pin.x;
        node.fy = pin.y;
        node.x = pin.x;
        node.y = pin.y;
      }
      node.x = Math.min(w - PAD, Math.max(PAD, node.x));
      node.y = Math.min(h - PAD, Math.max(PAD, node.y));
    }
    if (minor) return;
    alpha = Math.max(alpha, 0.2);
  }

  function step(): boolean {
    if (alpha <= ALPHA_REST) return false;
    const list = [...nodes.values()];
    const n = list.length;
    if (n === 0) {
      alpha = 0;
      return false;
    }
    if (alpha < INTERACTIVE_ALPHA) {
      for (const node of list) {
        node.vx = 0;
        node.vy = 0;
        if (node.fx !== null && node.fy !== null) {
          node.x = node.fx;
          node.y = node.fy;
        }
      }
      collide(list);
      alpha *= ALPHA_DECAY;
      return alpha > ALPHA_REST;
    }
    // Classic Fruchterman–Reingold displacements (the balance that spreads a
    // homelab-sized graph nicely), smoothed through a velocity blend so live
    // interaction reads as motion instead of teleports.
    const k = 1.02 * Math.sqrt((w * h) / n);
    const fx = new Float64Array(n);
    const fy = new Float64Array(n);
    const index = new Map<SimNode, number>();
    list.forEach((node, i) => index.set(node, i));
    for (let i = 0; i < n; i++) {
      const a = list[i];
      for (let j = i + 1; j < n; j++) {
        const b = list[j];
        let vx = a.x - b.x;
        let vy = a.y - b.y;
        let d2 = vx * vx + vy * vy;
        if (d2 < 1e-4) {
          vx = 0.011 * (i - j);
          vy = 0.017 * (i + 1);
          d2 = vx * vx + vy * vy;
        }
        const f = (k * k) / d2;
        fx[i] += vx * f;
        fy[i] += vy * f;
        fx[j] -= vx * f;
        fy[j] -= vy * f;
      }
      fx[i] += (w / 2 - a.x) * 0.04;
      fy[i] += (h / 2 - a.y) * 0.04;
    }
    for (const [a, b] of springs) {
      const i = index.get(a)!;
      const j = index.get(b)!;
      const vx = a.x - b.x;
      const vy = a.y - b.y;
      const pull = Math.hypot(vx, vy) / k;
      fx[i] -= vx * pull;
      fy[i] -= vy * pull;
      fx[j] += vx * pull;
      fy[j] += vy * pull;
    }
    // Temperature: hot systems take big steps, cooling ones settle gently.
    const cap = 1 + 34 * alpha;
    const deadzone = alpha < 0.5 ? FORCE_DEADZONE : 0;
    for (let i = 0; i < n; i++) {
      const node = list[i];
      if (node.fx !== null && node.fy !== null) {
        node.x = node.fx;
        node.y = node.fy;
        node.vx = 0;
        node.vy = 0;
        continue;
      }
      const len = Math.hypot(fx[i], fy[i]) || 1;
      let stepLen = Math.min(len, cap);
      if (stepLen < deadzone) stepLen = 0;
      node.vx = node.vx * (1 - FRICTION) + (fx[i] / len) * stepLen * FRICTION;
      node.vy = node.vy * (1 - FRICTION) + (fy[i] / len) * stepLen * FRICTION;
      if (Math.abs(node.vx) + Math.abs(node.vy) < SLEEP_SPEED) {
        node.vx = 0;
        node.vy = 0;
        continue;
      }
      node.x = Math.min(w - PAD, Math.max(PAD, node.x + node.vx));
      node.y = Math.min(h - PAD, Math.max(PAD, node.y + node.vy));
    }
    collide(list);
    alpha *= ALPHA_DECAY;
    return alpha > ALPHA_REST;
  }

  // Collision floor keeps labels legible whatever the springs decide.
  function collide(list: SimNode[]): void {
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const a = list[i];
        const b = list[j];
        let vx = b.x - a.x;
        let vy = b.y - a.y;
        let d = Math.hypot(vx, vy);
        if (d >= MIN_DIST) continue;
        if (d < 1e-4) {
          vx = 1;
          vy = 0;
          d = 1;
        }
        const push = (MIN_DIST - d) / d / 2;
        const aFree = a.fx === null ? 1 : 0;
        const bFree = b.fx === null ? 1 : 0;
        if (aFree + bFree === 0) continue;
        const share = aFree + bFree;
        if (aFree) {
          a.x = Math.min(w - PAD, Math.max(PAD, a.x - (vx * push * 2 * aFree) / share));
          a.y = Math.min(h - PAD, Math.max(PAD, a.y - (vy * push * 2 * aFree) / share));
        }
        if (bFree) {
          b.x = Math.min(w - PAD, Math.max(PAD, b.x + (vx * push * 2 * bFree) / share));
          b.y = Math.min(h - PAD, Math.max(PAD, b.y + (vy * push * 2 * bFree) / share));
        }
      }
    }
  }

  function settle(maxSteps = 400): void {
    alpha = Math.max(alpha, 1);
    for (let i = 0; i < maxSteps && step(); i++) {
      // step() drives the loop.
    }
    alpha = 0;
  }

  return {
    nodes,
    setGraph,
    resize,
    step,
    settle,
    reheat(next = 0.3) {
      alpha = Math.max(alpha, next);
    },
    drag(id, x, y) {
      const node = nodes.get(id);
      if (!node) return;
      node.fx = Math.min(w - PAD, Math.max(PAD, x));
      node.fy = Math.min(h - PAD, Math.max(PAD, y));
      // Barely warm: enough for direct neighbors to give way, far below the
      // temperature where the rest of the field starts to wander.
      alpha = Math.max(alpha, 0.07);
    },
    release(id) {
      if (!nodes.has(id)) return;
      // The pin stays: a dragged node holds the spot you gave it and the
      // rest of the constellation relaxes around it.
      alpha = Math.max(alpha, 0.05);
    },
    positions() {
      const out = new Map<string, XY>();
      for (const node of nodes.values()) {
        out.set(node.id, {
          x: Math.round(node.x * 100) / 100,
          y: Math.round(node.y * 100) / 100,
        });
      }
      return out;
    },
  };
}

/** Settled snapshot — the initial layout, and what the unit tests pin down. */
export function computeLayout(
  ids: readonly string[],
  links: ReadonlyArray<readonly [string, string]>,
  width: number,
  height: number,
  pinned: Readonly<Record<string, XY>> = {},
): Map<string, XY> {
  const sim = createSimulation(width, height);
  sim.setGraph(ids, links, pinned);
  sim.settle();
  return sim.positions();
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
