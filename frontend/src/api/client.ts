import type { MetricsResponse, NodeInfo, Snapshot } from './types';

const BASE = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${init?.method ?? 'GET'} ${path} → ${response.status}`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  snapshot: () => request<Snapshot>('/snapshot'),
  nodes: () => request<NodeInfo[]>('/nodes'),
  node: (uuid: string) => request<NodeInfo>(`/nodes/${uuid}`),
  patchNode: (uuid: string, body: { name?: string; approve?: boolean }) =>
    request<NodeInfo>(`/nodes/${uuid}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteNode: (uuid: string) => request<void>(`/nodes/${uuid}`, { method: 'DELETE' }),
  metrics: (node: string, names: string[], fromTs: number, toTs?: number) => {
    const params = new URLSearchParams({ node, m: names.join(','), from: String(fromTs) });
    if (toTs) params.set('to', String(toTs));
    return request<MetricsResponse>(`/metrics?${params}`);
  },
};
