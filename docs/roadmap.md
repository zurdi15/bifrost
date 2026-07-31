# Roadmap

All planned phases are built:

- **F0 — Foundation**: monorepo, design system + Storybook, multi-arch Dockerfiles, CI,
  hub skeleton with Alembic + EventBus, agent skeleton.
- **F1 — Nodes & live metrics**: protocol v1 (enroll, seq/ack with ring-buffer resume,
  heartbeat), system collectors, batched metrics store, UI WebSocket, node cards with
  heartbeat pulse / gauges / streaming sparklines / down flatline, node detail with hero
  morph.
- **F2 — Docker discovery**: unversioned Engine-API client over the socket, live lifecycle
  events + debounced reconcile, `bifrost.*` labels, Services section.
- **F3 — Time series**: raw→1m→1h downsampler with retention, res=auto queries,
  filesystems with NFS stale detection, uPlot history panels with zoom.
- **F4 — Disks**: smartctl JSON collector, per-serial disk upsert + temperature history,
  Storage view with SMART detail and pre-fail highlighting.
- **F5 — Kubernetes**: agent-side cluster detection (k3s/kubeadm/k0s markers), hub-side
  auto-registration with localhost URL rewrite, per-cluster inventory sync,
  CronJob/Job run history with events, Jobs view.
- **F6 — Agentless endpoints**: http/tcp/ping checks from the hub (the HAOS path),
  latency history, endpoint node cards, inline creation form.
- **F7 — Widgets**: hub-side widget type registry (weather via cached Open-Meteo proxy,
  clock), widgets CRUD + data dispatch, dashboard layout persistence, Ambient section
  with edit mode (add/reorder/resize/configure/remove).
- **F8 — Alerting**: EventBus-subscribing rules engine with per-subject cooldowns,
  ntfy + webhook notifiers, rules CRUD + test endpoint, Alerts view.

## Future ideas

- Streaming Kubernetes watches (resourceVersion resume) instead of the 30s poll.
- Home Assistant API widget (entities via long-lived token) and a HAOS add-on wrapping
  the agent image ([haos.md](haos.md)).
- Per-container CPU/memory stats from the Docker stats API.
- Dashboard widgets for storage/backup summaries.
- Light theme (`html.bf-light` redefinition — tokens are ready).

There is deliberately **no auth phase**: the dashboard is open by design; protection
belongs to the network layer.
