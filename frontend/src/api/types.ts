export interface LiveSnapshot {
  ts: number;
  samples: Record<string, number>;
}

export interface NodeInfo {
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
}

export interface Snapshot {
  seq: number;
  nodes: NodeInfo[];
  containers: Record<string, ContainerInfo[]>;
}

export interface WsEvent {
  seq: number;
  topic: string;
  data: Record<string, unknown>;
}

export interface MetricsResponse {
  node: string;
  from: number;
  to: number;
  res: string;
  series: Record<string, [number, number][]>;
}

export type ConnectionState = 'connecting' | 'live' | 'reconnecting' | 'offline';
