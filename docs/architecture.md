# Architecture

```
 Go agents (1/node) ───WS push───► HUB (FastAPI) ───REST + WS───► Vue SPA
   /proc /sys docker.sock smartctl │  ├─ EventBus → events table + UI broadcast
                                   │  ├─ MetricsWriter (batched) → metrics.db
 k8s API ◄──watch── K8sWatcher ────┤  ├─ Checker (ping/http, agentless nodes)
 Open-Meteo ◄─cached proxy─ Widgets┘  └─ bifrost.db (state, config, layout)
```

## Components

### bifrost-agent (Go)

One per node, shipped only as a Docker container (alpine + smartmontools, static binary,
amd64 + arm64). Fully stateless: node identity is `sha256(host /etc/machine-id)` (fallback:
hostname + MAC addresses), so the container can be destroyed and recreated freely.

Collectors run on independent tickers and publish into a channel; the transport layer
serializes, numbers (`seq`), buffers (ring, ~2048 frames) and sends over a single outbound
WebSocket. Reconnection uses exponential backoff with jitter (1s → 60s cap, forever).

- system: CPU %, load, memory, swap, network rates, temperatures, uptime — every 10s
- filesystems: every 60s; NFS statfs runs in a goroutine with a timeout → `stale` flag,
  a hung mount never blocks the loop (phase 3)
- docker: event stream in real time + full reconcile every 60s (phase 2)
- smart: `smartctl --scan --json` + per-device `smartctl -a -j` every 30min (phase 4)
- k8s detection: kubeconfig markers + port 6443 on the host rootfs (phase 5)

### bifrost-hub (Python)

FastAPI app, one container, one `/data` volume. Ingests agent streams, maintains state in
`bifrost.db` (Alembic-migrated), time series in `metrics.db` (code-managed schema, WAL,
single batched writer task — 5s or 500 rows per transaction). Serves the SPA and the UI
WebSocket.

**EventBus** (`app/bus.py`): in-process asyncio pub/sub. Every state change (node status,
container event, cronjob run, disk update) is published once; subscribers are the UI
broadcaster, the `events` timeline table, and — later — the alerting engine.

**Node-down detection**: TCP close of the agent socket → `offline` immediately. Application
heartbeat every 15s catches half-open sockets: 2 missed → `degraded`, 3 → `offline`
(worst case 45s).

### Kubernetes (phase 5)

Agents *detect* clusters on their node (k3s/kubeadm/k0s kubeconfig markers, port 6443) and
report `k8s_detected`; the hub auto-registers the cluster, rewriting a localhost API server
URL to the node address seen on the agent's WebSocket connection. The hub — not the agents —
runs one watcher per cluster (httpx streaming watch + full relist every 5min) over
read-only RBAC. Manually-added clusters (kubeconfig mount or url+token+ca) are equally
supported for clusters with no agent.

### Tailnet (optional)

With a Tailscale admin-API token configured (`BIFROST_TAILSCALE_API_KEY`), a
hub-side poller sweeps devices + the ACL policy every 60s and evaluates who
can reach whom (ports included) best-effort: groups, tags, hosts, CIDRs,
`autogroup:member/tagged/self`, and `autogroup:internet` through exit nodes.
Selectors it cannot ground to devices are surfaced as `unresolved` — the UI
flags the map as partial instead of lying. The graph lives in memory only
(re-derived each sweep, stale-served on API errors); device online/offline
transitions ride the EventBus like every other state change. A canned
document (`BIFROST_TAILNET_FIXTURE`) replaces the API for demos and tests.

### Agentless nodes (phase 6)

`kind='endpoint'` nodes with ping/http/tcp checks run from the hub. This is how a Home
Assistant OS box (which can't easily run arbitrary containers) is monitored; deeper HA
integration is a widget over the HA REST API (phase 7), and a HAOS add-on wrapping the
agent image is documented as a community path in [haos.md](haos.md).

## Storage

Two SQLite files, deliberately separate so metric churn (checkpoints, retention deletes,
vacuum) never touches config, and config backup stays a KB-sized copy:

- `bifrost.db` — nodes, containers, disks, fs mounts, k8s inventory, endpoint checks,
  widgets, dashboard layout, settings, events. Alembic migrations.
- `metrics.db` — interned metric names + `samples_raw` / `samples_1m` / `samples_1h`
  (WITHOUT ROWID, PK `(node_id, metric_id, ts)`). Downsampling and retention run as a
  background task (defaults: raw 24h, 1m 14d, 1h 2y). `PRAGMA user_version` schema.

Timestamps are integer epoch **seconds** UTC everywhere. The hub stamps receive time and
trusts the agent's clock only within 30s of skew.
