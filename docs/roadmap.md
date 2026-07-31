# Roadmap

Built phases:

- **F0 — Foundation**: monorepo, design system + Storybook, multi-arch Dockerfiles, CI,
  hub skeleton with Alembic + EventBus, agent skeleton.
- **F1 — Nodes & live metrics**: protocol v1 (enroll, seq/ack, heartbeat), system
  collectors, batched metrics store (raw), UI WebSocket, dashboard node cards
  (heartbeat pulse, gauges, streaming sparklines, down flatline), node detail with hero
  morph.

Upcoming:

- **F2 — Docker discovery**: container list + real-time events, `bifrost.*` labels
  (icon/url/group/hide), Services section in the dashboard.
- **F3 — Full time series**: 1m/1h downsampler, retention + incremental vacuum,
  `res=auto` queries, fs mounts (NFS `stale` flag), uPlot panels with zoom and live
  append in node detail.
- **F4 — Disks**: SMART collector, storage view (capacity bars, expandable SMART
  attributes), disk summary widget.
- **F5 — Kubernetes**: `k8s_detected` autodiscovery + auto-registration (localhost API
  URL rewrite, `tls-san` guidance, per-cluster `insecure_skip_verify` toggle), hub-side
  watchers (workloads, pods, services, ingresses), **CronJobs + Job runs history**
  (backup monitoring), Jobs view with timeline.
- **F6 — Agentless endpoints**: ping/http/tcp checks from the hub (Home Assistant OS,
  routers, anything).
- **F7 — Widgets & layout editing**: widget registry (folder-per-widget manifest),
  clock, weather (Open-Meteo proxied + cached by the hub, no API key), Home Assistant
  API widget, edit mode (drag reorder FLIP, size presets 1x1/2x1/2x2, catalog),
  layout persisted in the hub.
- **F8 — Alerting**: rules engine subscribing to the EventBus, ntfy/webhook notifiers.

There is deliberately **no auth phase**: the dashboard is open by design; protection
belongs to the network layer.
