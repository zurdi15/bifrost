import { defineStore } from 'pinia';
import { computed, reactive, ref, shallowRef } from 'vue';

import { api } from '@/api/client';
import type { ConnectionState, ContainerInfo, DiskInfo, FsMount, NodeInfo, WsEvent } from '@/api/types';
import { UiSocket } from '@/api/ws';
import { useMetricsStore } from '@/stores/metrics';

export const useLiveStore = defineStore('live', () => {
  const connection = ref<ConnectionState>('connecting');
  const retryAt = ref<number | null>(null);
  const nodes = reactive(new Map<string, NodeInfo>());
  const containers = reactive(new Map<string, ContainerInfo[]>());
  const k8sServices = ref<ContainerInfo[]>([]);
  const fs = reactive(new Map<string, FsMount[]>());
  const disks = reactive(new Map<string, DiskInfo[]>());
  const lastSeq = ref(0);
  // Bumped on any k8s.* event so views can refetch their REST data.
  const k8sVersion = ref(0);
  // Bumped when bookmarks.yml resyncs on the hub.
  const bookmarksVersion = ref(0);
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
  const allServices = computed(() => [...containers.values()].flat().concat(k8sServices.value));
  const containerList = computed(() =>
    allServices.value
      .filter((c) => !c.meta.hide)
      .sort(
        (a, b) =>
          (a.meta.group ?? '￿').localeCompare(b.meta.group ?? '￿') ||
          a.name.localeCompare(b.name),
      ),
  );
  const hiddenContainers = computed(() =>
    allServices.value
      .filter((c) => c.meta.hide)
      .sort((a, b) => a.name.localeCompare(b.name)),
  );

  async function snapshot(): Promise<void> {
    const snap = await api.snapshot();
    nodes.clear();
    for (const node of snap.nodes) {
      nodes.set(node.uuid, node);
      if (node.live) metrics.ingest(node.uuid, node.live.samples);
    }
    containers.clear();
    for (const [uuid, list] of Object.entries(snap.containers ?? {})) {
      containers.set(uuid, list);
    }
    k8sServices.value = snap.k8s_services ?? [];
    disks.clear();
    for (const [uuid, list] of Object.entries(snap.disks ?? {})) {
      disks.set(uuid, list);
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
    } else if (event.topic === 'containers.updated') {
      containers.set(event.data.uuid as string, event.data.containers as ContainerInfo[]);
    } else if (event.topic === 'disk.updated') {
      disks.set(event.data.uuid as string, event.data.disks as DiskInfo[]);
    } else if (event.topic.startsWith('k8s.')) {
      k8sVersion.value += 1;
      // Inventory changed: refresh the k8s services on the dashboard.
      if (event.topic === 'k8s.synced') void snapshot();
    } else if (event.topic === 'bookmarks.updated') {
      bookmarksVersion.value += 1;
    } else if (event.topic === 'fs.updated') {
      fs.set(event.data.uuid as string, event.data.mounts as FsMount[]);
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
    containers,
    k8sServices,
    fs,
    disks,
    nodeList,
    containerList,
    hiddenContainers,
    upCount,
    downNodes,
    lastSeq,
    k8sVersion,
    bookmarksVersion,
    connect,
    disconnect,
    applyEvent,
    snapshot,
  };
});
