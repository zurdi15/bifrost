import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { NodeInfo } from '@/api/types';

vi.mock('@/api/client', () => ({
  api: {
    snapshot: vi.fn(),
  },
}));

import { api } from '@/api/client';
import { useLiveStore } from './live';

function fakeNode(uuid: string, overrides: Partial<NodeInfo> = {}): NodeInfo {
  return {
    uuid,
    name: uuid,
    kind: 'agent',
    status: 'online',
    os: 'linux',
    arch: 'amd64',
    agent_version: '0.1.0',
    boot_ts: 1000,
    labels: {},
    last_seen: 2000,
    created_at: 1000,
    live: null,
    ...overrides,
  };
}

describe('live store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(api.snapshot).mockReset();
  });

  it('loads the snapshot into the node map', async () => {
    const store = useLiveStore();
    vi.mocked(api.snapshot).mockResolvedValue({
      seq: 7,
      nodes: [fakeNode('a'), fakeNode('b', { status: 'offline' })],
      containers: {},
      disks: {},
    });
    await store.snapshot();
    expect(store.nodeList).toHaveLength(2);
    expect(store.upCount).toBe(1);
    expect(store.downNodes.map((n) => n.uuid)).toEqual(['b']);
    expect(store.lastSeq).toBe(7);
  });

  it('applies node.status deltas in place', async () => {
    const store = useLiveStore();
    vi.mocked(api.snapshot).mockResolvedValue({ seq: 1, nodes: [fakeNode('a')], containers: {}, disks: {} });
    await store.snapshot();

    store.applyEvent({ seq: 2, topic: 'node.status', data: { uuid: 'a', status: 'offline' } });
    expect(store.nodes.get('a')?.status).toBe('offline');
    expect(store.lastSeq).toBe(2);
  });

  it('applies metrics.live to node state', async () => {
    const store = useLiveStore();
    vi.mocked(api.snapshot).mockResolvedValue({ seq: 1, nodes: [fakeNode('a')], containers: {}, disks: {} });
    await store.snapshot();

    store.applyEvent({
      seq: 2,
      topic: 'metrics.live',
      data: { uuid: 'a', ts: 123, samples: { 'cpu.pct': 55 } },
    });
    expect(store.nodes.get('a')?.live?.samples['cpu.pct']).toBe(55);
  });

  it('re-snapshots on a seq gap', async () => {
    const store = useLiveStore();
    vi.mocked(api.snapshot).mockResolvedValue({ seq: 1, nodes: [fakeNode('a')], containers: {}, disks: {} });
    await store.snapshot();
    expect(api.snapshot).toHaveBeenCalledTimes(1);

    // seq jumps 2 → 9: something was dropped, full refresh required.
    store.applyEvent({ seq: 9, topic: 'node.status', data: { uuid: 'a', status: 'online' } });
    expect(api.snapshot).toHaveBeenCalledTimes(2);
  });

  it('re-snapshots when an unknown node reports status', async () => {
    const store = useLiveStore();
    vi.mocked(api.snapshot).mockResolvedValue({ seq: 1, nodes: [], containers: {}, disks: {} });
    await store.snapshot();

    store.applyEvent({ seq: 2, topic: 'node.status', data: { uuid: 'ghost', status: 'online' } });
    expect(api.snapshot).toHaveBeenCalledTimes(2);
  });

  it('applies containers.updated per node', async () => {
    const store = useLiveStore();
    vi.mocked(api.snapshot).mockResolvedValue({ seq: 1, nodes: [fakeNode('a')], containers: {}, disks: {} });
    await store.snapshot();

    store.applyEvent({
      seq: 2,
      topic: 'containers.updated',
      data: {
        uuid: 'a',
        containers: [
          {
            id: 'c1', name: 'romm', image: 'x', state: 'running', health: '',
            ports: [], meta: { group: 'media' }, started_at: 0, updated_at: 0,
            node_uuid: 'a', node_name: 'a',
          },
          {
            id: 'c2', name: 'secret', image: 'x', state: 'running', health: '',
            ports: [], meta: { hide: true }, started_at: 0, updated_at: 0,
            node_uuid: 'a', node_name: 'a',
          },
        ],
      },
    });
    expect(store.containers.get('a')).toHaveLength(2);
    // hidden containers never reach the visible list
    expect(store.containerList.map((c) => c.name)).toEqual(['romm']);
  });
});
