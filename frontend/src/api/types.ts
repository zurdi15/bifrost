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

export interface Snapshot {
  seq: number;
  nodes: NodeInfo[];
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
