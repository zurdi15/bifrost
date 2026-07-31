import { defineStore } from 'pinia';
import { computed, reactive, ref, shallowRef } from 'vue';

import { api } from '@/api/client';
import type { ConnectionState, NodeInfo, WsEvent } from '@/api/types';
import { UiSocket } from '@/api/ws';
import { useMetricsStore } from '@/stores/metrics';

export const useLiveStore = defineStore('live', () => {
  const connection = ref<ConnectionState>('connecting');
  const retryAt = ref<number | null>(null);
  const nodes = reactive(new Map<string, NodeInfo>());
  const lastSeq = ref(0);
  const socket = shallowRef<UiSocket | null>(null);

  const metrics = useMetricsStore();

  const nodeList = computed(() =>
    [...nodes.values()].sort((a, b) => a.created_at - b.created_at),
  );
  const upCount = computed(
    () => nodeList.value.filter((n) => n.status === 'online').length,
  );
  const downNodes = computed(() =>
    nodeList.value.filter((n) => n.status === 'offline' || n.status === 'degraded'),
  );

  async function snapshot(): Promise<void> {
    const snap = await api.snapshot();
    nodes.clear();
    for (const node of snap.nodes) {
      nodes.set(node.uuid, node);
      if (node.live) metrics.ingest(node.uuid, node.live.samples);
    }
    lastSeq.value = snap.seq;
  }

  function applyEvent(event: WsEvent): void {
    // A gap means the bus dropped frames for us (slow consumer) or we missed
    // messages across a reconnect: state may be stale → full re-snapshot.
    if (lastSeq.value > 0 && event.seq > lastSeq.value + 1) {
      void snapshot();
    }
    lastSeq.value = Math.max(lastSeq.value, event.seq);

    if (event.topic === 'node.status') {
      const uuid = event.data.uuid as string;
      const status = event.data.status as string;
      const node = nodes.get(uuid);
      if (node) {
        node.status = status;
        node.last_seen = Math.floor(Date.now() / 1000);
      } else {
        void snapshot(); // unknown node appeared: fetch everything
      }
    } else if (event.topic === 'metrics.live') {
      const uuid = event.data.uuid as string;
      const samples = event.data.samples as Record<string, number>;
      const node = nodes.get(uuid);
      if (node) {
        node.live = { ts: event.data.ts as number, samples };
      }
      metrics.ingest(uuid, samples);
    }
  }

  function connect(): void {
    if (socket.value) return;
    connection.value = 'connecting';
    const ws = new UiSocket({
      onOpen: () => {
        connection.value = 'live';
        retryAt.value = null;
        void snapshot();
      },
      onDown: (retryInMs) => {
        connection.value = 'reconnecting';
        retryAt.value = Date.now() + retryInMs;
      },
      onEvent: applyEvent,
    });
    socket.value = ws;
    ws.connect();
  }

  function disconnect(): void {
    socket.value?.close();
    socket.value = null;
    connection.value = 'offline';
  }

  return {
    connection,
    retryAt,
    nodes,
    nodeList,
    upCount,
    downNodes,
    lastSeq,
    connect,
    disconnect,
    applyEvent,
    snapshot,
  };
});
