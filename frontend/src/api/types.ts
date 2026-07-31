export interface LiveSnapshot {
  ts: number;
  samples: Record<string, number>;
}

export interface EndpointCheckInfo {
  id: number;
  kind: 'ping' | 'http' | 'tcp';
  target: string;
  interval_s: number;
  last_ok: boolean | null;
  last_latency_ms: number | null;
  last_checked: number | null;
}

export interface NodeInfo {
  checks?: EndpointCheckInfo[] | null;
  uuid: string;
  name: string;
  kind: 'agent' | 'endpoint';
  status: string;
  os: string | null;
  arch: string | null;
  agent_version: string | null;
  boot_ts: number | null;
  labels: Record<string, string>;
  last_seen: number | null;
  created_at: number;
  live: LiveSnapshot | null;
}

export interface ContainerMeta {
  /** Custom display name (UI override; the container keeps its real name). */
  name?: string;
  icon?: string;
  url?: string;
  group?: string;
  hide?: boolean;
}

export interface ContainerInfo {
  id: string;
  name: string;
  image: string | null;
  state: string | null;
  health: string | null;
  ports: string[];
  meta: ContainerMeta;
  started_at: number | null;
  updated_at: number;
  node_uuid: string;
  node_name: string;
  /** 'docker' container or 'k8s' workload — both render as service cards. */
  source?: 'docker' | 'k8s';
}

export interface BookmarkInfo {
  id: number;
  name: string;
  url: string;
  icon: string | null;
  group: string | null;
  position: number;
  /** 'file' rows come from bookmarks.yml and are read-only in the UI. */
  source: 'ui' | 'file';
}

export interface Snapshot {
  seq: number;
  nodes: NodeInfo[];
  containers: Record<string, ContainerInfo[]>;
  disks: Record<string, DiskInfo[]>;
  k8s_services?: ContainerInfo[];
}

export interface WsEvent {
  seq: number;
  topic: string;
  data: Record<string, unknown>;
}

export interface FsMount {
  mountpoint: string;
  device: string | null;
  fstype: string | null;
  total_bytes: number | null;
  used_bytes: number | null;
  used_pct: number | null;
  stale: boolean;
  updated_at: number;
}

export interface DiskInfo {
  device: string;
  model: string | null;
  serial: string;
  kind: string | null;
  capacity_bytes: number | null;
  smart_status: string | null;
  temp_c: number | null;
  power_on_hours: number | null;
  realloc_sectors: number | null;
  pending_sectors: number | null;
  wear_pct: number | null;
  updated_at: number;
  node_uuid: string;
  node_name: string;
}

export type Resolution = 'auto' | 'raw' | '1m' | '1h';

export interface MetricsResponse {
  node: string;
  from: number;
  to: number;
  /** raw rows: [ts, value] · aggregated rows: [ts, avg, min, max] */
  res: Exclude<Resolution, 'auto'>;
  series: Record<string, number[][]>;
}

export type ConnectionState = 'connecting' | 'live' | 'reconnecting' | 'offline';
