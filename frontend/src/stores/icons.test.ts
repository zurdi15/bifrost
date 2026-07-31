import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/client', () => ({
  api: {
    resolveIcons: vi.fn(),
  },
}));

import { api } from '@/api/client';
import { iconCandidates } from '@/utils/autoIcon';
import { useIconStore } from './icons';

describe('iconCandidates', () => {
  it('tries name, de-suffixed name and image basename, deduped', () => {
    expect(
      iconCandidates({ name: 'homelab-pihole-1', image: 'pihole/pihole:2024.05' }),
    ).toEqual(['homelab-pihole-1', 'homelab-pihole', 'pihole']);
    expect(iconCandidates({ name: 'romm', image: 'ghcr.io/rommapp/romm@sha256:x' })).toEqual([
      'romm',
    ]);
    expect(iconCandidates({ name: 'zerobyte', image: null })).toEqual(['zerobyte']);
  });

  it('prefers the custom display name when present', () => {
    expect(
      iconCandidates({ name: 'stack-webapp-1', image: null, meta: { name: 'Grafana' } }),
    ).toEqual(['grafana', 'stack-webapp-1', 'stack-webapp']);
  });
});

describe('icon store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(api.resolveIcons).mockReset();
  });

  it('batches lookups and resolves through candidates', async () => {
    vi.useFakeTimers();
    const store = useIconStore();
    vi.mocked(api.resolveIcons).mockResolvedValue({
      pihole: 'https://cdn.example/pi-hole.svg',
      romm: 'https://cdn.example/romm.svg',
      zerobyte: null,
    });

    const pihole = { name: 'pihole', image: 'pihole/pihole:2024' };
    const romm = { name: 'romm', image: null };
    const zerobyte = { name: 'zerobyte', image: null };
    store.ensure(pihole);
    store.ensure(romm);
    store.ensure(zerobyte);
    expect(store.iconFor(pihole)).toBeNull(); // not resolved yet

    await vi.runAllTimersAsync();
    // One batched request for every unknown candidate.
    expect(api.resolveIcons).toHaveBeenCalledTimes(1);
    expect(store.iconFor(pihole)).toBe('https://cdn.example/pi-hole.svg');
    expect(store.iconFor(romm)).toBe('https://cdn.example/romm.svg');
    expect(store.iconFor(zerobyte)).toBeNull();

    // Known names (hits and misses) never re-query.
    store.ensure(pihole);
    store.ensure(zerobyte);
    await vi.runAllTimersAsync();
    expect(api.resolveIcons).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it('leaves names unset on failure so they retry later', async () => {
    vi.useFakeTimers();
    const store = useIconStore();
    vi.mocked(api.resolveIcons).mockRejectedValueOnce(new Error('down'));
    store.ensure({ name: 'romm', image: null });
    await vi.runAllTimersAsync();
    expect(store.resolved.has('romm')).toBe(false);

    vi.mocked(api.resolveIcons).mockResolvedValue({ romm: 'https://cdn.example/romm.svg' });
    store.ensure({ name: 'romm', image: null });
    await vi.runAllTimersAsync();
    expect(store.iconFor({ name: 'romm', image: null })).toBe('https://cdn.example/romm.svg');
    vi.useRealTimers();
  });
});
