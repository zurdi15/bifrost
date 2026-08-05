import { describe, expect, it } from 'vitest';

import { computeLayout, mergeEdges } from './useTailnetLayout';

const IDS = ['a', 'b', 'c', 'd', 'e'];
const LINKS: Array<[string, string]> = [
  ['a', 'b'],
  ['b', 'a'],
  ['b', 'c'],
  ['d', 'e'],
];

describe('computeLayout', () => {
  it('is deterministic', () => {
    const first = computeLayout(IDS, LINKS, 1000, 620);
    const second = computeLayout(IDS, LINKS, 1000, 620);
    expect([...first.entries()]).toEqual([...second.entries()]);
  });

  it('keeps every node inside the padded canvas, without NaN', () => {
    const layout = computeLayout(IDS, LINKS, 1000, 620);
    expect(layout.size).toBe(IDS.length);
    for (const { x, y } of layout.values()) {
      expect(Number.isFinite(x) && Number.isFinite(y)).toBe(true);
      expect(x).toBeGreaterThanOrEqual(64);
      expect(x).toBeLessThanOrEqual(1000 - 64);
      expect(y).toBeGreaterThanOrEqual(64);
      expect(y).toBeLessThanOrEqual(620 - 64);
    }
  });

  it('separates nodes', () => {
    const layout = computeLayout(IDS, LINKS, 1000, 620);
    const points = [...layout.values()];
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        expect(Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y)).toBeGreaterThan(
          40,
        );
      }
    }
  });

  it('respects pinned positions', () => {
    const layout = computeLayout(['x', 'y', 'internet'], [['x', 'internet']], 1000, 620, {
      internet: { x: 500, y: 70 },
    });
    expect(layout.get('internet')).toEqual({ x: 500, y: 70 });
  });

  it('handles a single node and an empty graph', () => {
    expect(computeLayout([], [], 1000, 620).size).toBe(0);
    const alone = computeLayout(['solo'], [], 1000, 620).get('solo');
    expect(alone && Number.isFinite(alone.x)).toBe(true);
  });
});

describe('mergeEdges', () => {
  it('folds both directions of a pair into one link', () => {
    const pairs = mergeEdges([
      { src: 'b', dst: 'a', ports: ['22/tcp'] },
      { src: 'a', dst: 'b', ports: ['*'] },
      { src: 'a', dst: 'c', ports: ['443'] },
    ]);
    expect(pairs).toEqual([
      { a: 'a', b: 'b', ab: ['*'], ba: ['22/tcp'] },
      { a: 'a', b: 'c', ab: ['443'], ba: null },
    ]);
  });
});
