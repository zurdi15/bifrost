import { describe, expect, it } from 'vitest';

import { formatBytes, formatDelta, formatUptime } from './format';

describe('formatBytes', () => {
  it('formats across units', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(1024)).toBe('1.0 KiB');
    expect(formatBytes(5.5 * 1024 ** 3)).toBe('5.5 GiB');
  });

  it('handles invalid input', () => {
    expect(formatBytes(-1)).toBe('—');
    expect(formatBytes(NaN)).toBe('—');
  });
});

describe('formatUptime', () => {
  const now = 1_000_000;

  it('renders days and hours', () => {
    expect(formatUptime(now - 2 * 86400 - 3 * 3600, now)).toBe('2d 3h');
  });

  it('renders hours and minutes', () => {
    expect(formatUptime(now - 3 * 3600 - 20 * 60, now)).toBe('3h 20m');
  });

  it('renders minutes only', () => {
    expect(formatUptime(now - 5 * 60, now)).toBe('5m');
  });

  it('handles missing or future boot ts', () => {
    expect(formatUptime(null, now)).toBe('—');
    expect(formatUptime(now + 100, now)).toBe('—');
  });
});

describe('formatDelta', () => {
  it('renders compact spans', () => {
    expect(formatDelta(30)).toBe('<1m');
    expect(formatDelta(5 * 60)).toBe('5m');
    expect(formatDelta(2 * 86400 + 3 * 3600)).toBe('2d 3h');
  });

  it('handles invalid input', () => {
    expect(formatDelta(-5)).toBe('—');
    expect(formatDelta(NaN)).toBe('—');
  });
});
