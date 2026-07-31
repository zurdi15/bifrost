import type { Meta, StoryObj } from '@storybook/vue3-vite';

import type { NodeInfo } from '@/api/types';
import { useMetricsStore } from '@/stores/metrics';

import NodeCard from './NodeCard.vue';

const meta: Meta = {
  title: 'App/NodeCard',
  component: NodeCard,
};
export default meta;

function node(overrides: Partial<NodeInfo>): NodeInfo {
  return {
    uuid: 'story-node',
    name: 'mimir',
    kind: 'agent',
    status: 'online',
    url: null,
    os: 'linux',
    arch: 'arm64',
    agent_version: '0.1.0',
    boot_ts: Math.floor(Date.now() / 1000) - 12 * 86400 - 4 * 3600,
    labels: {},
    last_seen: Math.floor(Date.now() / 1000) - 42,
    created_at: 0,
    live: {
      ts: Math.floor(Date.now() / 1000),
      samples: { 'cpu.pct': 37, 'mem.pct': 62, 'temp.cpu': 44 },
    },
    ...overrides,
  };
}

function seedMetrics(uuid: string) {
  const metrics = useMetricsStore();
  for (let i = 0; i < 60; i++) {
    metrics.ingest(uuid, {
      'cpu.pct': 40 + 25 * Math.sin(i / 6) + Math.random() * 10,
    });
  }
}

export const Online: StoryObj = {
  render: () => ({
    components: { NodeCard },
    setup() {
      seedMetrics('story-node');
      return { node: node({}) };
    },
    template: '<div style="width:320px"><NodeCard :node="node" /></div>',
  }),
};

export const Down: StoryObj = {
  render: () => ({
    components: { NodeCard },
    setup() {
      seedMetrics('down-node');
      return { node: node({ uuid: 'down-node', name: 'huginn', status: 'offline' }) };
    },
    template: '<div style="width:320px"><NodeCard :node="node" /></div>',
  }),
};
