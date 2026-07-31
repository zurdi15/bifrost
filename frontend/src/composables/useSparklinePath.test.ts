import { describe, expect, it } from 'vitest';

import { sparklinePath } from './useSparklinePath';

describe('sparklinePath', () => {
  it('returns empty paths under 2 points', () => {
    expect(sparklinePath([], 100, 30).line).toBe('');
    expect(sparklinePath([5], 100, 30).line).toBe('');
  });

  it('spans the full width', () => {
    const { line } = sparklinePath([0, 50, 100], 120, 30);
    expect(line.startsWith('M0 ')).toBe(true);
    expect(line).toContain('L120 ');
  });

  it('maps higher values to lower y (SVG coordinates)', () => {
    const { line } = sparklinePath([0, 100], 100, 30, { min: 0, max: 100, pad: 0 });
    expect(line).toBe('M0 30 L100 0');
  });

  it('handles flat series without dividing by zero', () => {
    const { line } = sparklinePath([42, 42, 42], 90, 30);
    expect(line).not.toContain('NaN');
    // Flat series renders mid-band.
    const ys = [...line.matchAll(/[ML][\d.]+ ([\d.]+)/g)].map((m) => Number(m[1]));
    expect(new Set(ys).size).toBe(1);
    expect(ys[0]).toBeGreaterThan(10);
    expect(ys[0]).toBeLessThan(20);
  });

  it('respects fixed min/max bounds', () => {
    const bounded = sparklinePath([50], 100, 30, { min: 0, max: 100 });
    expect(bounded.line).toBe('');
    const { lastY } = sparklinePath([25, 50], 100, 30, { min: 0, max: 100, pad: 0 });
    expect(lastY).toBe(15);
  });

  it('closes the area path to the baseline', () => {
    const { area } = sparklinePath([1, 2, 3], 100, 30);
    expect(area.endsWith('L100 30 L0 30 Z')).toBe(true);
  });
});
