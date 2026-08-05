// Tailnet section feed — mirrors the hub poller payload (app/tailnet/poller.py).

export const INTERNET_ID = 'internet';

export interface TailnetDevice {
  id: string;
  name: string;
  fqdn: string;
  hostname: string;
  ips: string[];
  os: string;
  user: string;
  tags: string[];
  online: boolean;
  last_seen: number;
  expires: number;
  key_expiry_disabled: boolean;
  client_version: string;
  update_available: boolean;
  authorized: boolean;
  external: boolean;
  exit_node: boolean;
  routes: string[];
  blocks_incoming: boolean;
}

export interface TailnetEdge {
  src: string;
  dst: string;
  ports: string[];
}

export interface TailnetPolicy {
  rules: number;
  groups: Record<string, number>;
  unresolved: string[];
}

export interface TailnetState {
  configured: boolean;
  error: string | null;
  source: 'api' | 'fixture' | '';
  tailnet: string;
  fetched_at: number;
  devices: TailnetDevice[];
  edges: TailnetEdge[];
  internet: boolean;
  policy: TailnetPolicy | null;
}

async function request(path: string, init?: RequestInit): Promise<TailnetState> {
  const response = await fetch(`/api/v1${path}`, init);
  if (!response.ok) {
    throw new Error(`${init?.method ?? 'GET'} ${path} → ${response.status}`);
  }
  return response.json();
}

export const fetchTailnet = (): Promise<TailnetState> => request('/tailnet');
export const refreshTailnet = (): Promise<TailnetState> =>
  request('/tailnet/refresh', { method: 'POST' });
