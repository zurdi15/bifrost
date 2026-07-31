import type {
  BookmarkInfo,
  ContainerInfo,
  FsMount,
  MetricsResponse,
  NodeInfo,
  Resolution,
  Snapshot,
} from './types';

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
  patchNode: (uuid: string, body: { name?: string; url?: string; approve?: boolean }) =>
    request<NodeInfo>(`/nodes/${uuid}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteNode: (uuid: string) => request<void>(`/nodes/${uuid}`, { method: 'DELETE' }),
  metrics: (node: string, names: string[], fromTs: number, toTs?: number, res: Resolution = 'auto') => {
    const params = new URLSearchParams({ node, m: names.join(','), from: String(fromTs), res });
    if (toTs) params.set('to', String(toTs));
    return request<MetricsResponse>(`/metrics?${params}`);
  },
  nodeFs: (uuid: string) => request<FsMount[]>(`/nodes/${uuid}/fs`),
  bookmarks: () => request<BookmarkInfo[]>('/bookmarks'),
  createBookmark: (body: { name: string; url: string; icon?: string; group?: string }) =>
    request<BookmarkInfo>('/bookmarks', { method: 'POST', body: JSON.stringify(body) }),
  patchBookmark: (
    id: number,
    body: { name?: string; url?: string; icon?: string; group?: string; position?: number },
  ) => request<BookmarkInfo>(`/bookmarks/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteBookmark: (id: number) => request<void>(`/bookmarks/${id}`, { method: 'DELETE' }),
  resolveIcons: (names: string[]) =>
    request<Record<string, string | null>>(`/icons?names=${encodeURIComponent(names.join(','))}`),
  putServiceMeta: (
    nodeUuid: string,
    containerName: string,
    body: { name?: string; icon?: string; url?: string; group?: string; hide?: boolean },
  ) =>
    request<ContainerInfo>(
      `/containers/${encodeURIComponent(nodeUuid)}/${encodeURIComponent(containerName)}/meta`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),
};
