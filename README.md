<p align="center">
  <img src="bifrost.svg" alt="" width="130" />
</p>
<p align="center">
  <img src="bifrost-logo.svg" alt="BIFROST" width="420" />
</p>

> The bridge between you and your homelab.

**Bifrost** is a self-hosted homelab dashboard built around two containers:

- **`bifrost-hub`** — FastAPI + SQLite + a Vue 3 SPA. Receives agent reports, stores state
  and metric history, and serves the dashboard.
- **`bifrost-agent`** — a tiny static Go binary (alpine + smartmontools image). One per node.
  Collects system metrics (CPU, memory, load, network, temperatures), discovers local Docker
  containers, reads disk SMART health, and detects Kubernetes clusters running on the node.

Agents connect **outbound** to the hub over a persistent WebSocket: no open ports on your
nodes, and node-down detection is instant (socket close + application heartbeat).

## Status

Early development. Current scope (phase 0–1): live node metrics, node cards with real-time
streaming, node detail view. See [docs/roadmap.md](docs/roadmap.md) for what comes next
(Docker discovery, Kubernetes autodiscovery, SMART, widgets, alerting).

## Quick start

```sh
# Hub (one instance, anywhere)
docker compose -f examples/docker-compose.hub.yml up -d

# Agent (one per node)
docker compose -f examples/docker-compose.agent.yml up -d
```

Set `BIFROST_ENROLL_TOKEN` on the hub and `BIFROST_AGENT_ENROLL_TOKEN` +
`BIFROST_AGENT_HUB_URL` on each agent. That's it — nodes appear in the dashboard as they
connect.

## Design principles

- **Infrastructure-agnostic.** Any mix of bare Docker hosts, NAS boxes, Raspberry Pis and
  Kubernetes clusters. Bifrost adapts to what it finds.
- **Push, not pull.** Agents dial the hub. Nodes never expose anything.
- **Open by design.** The dashboard has no authentication — protect it at the network layer
  (Tailscale, reverse proxy). Agent enrollment is token-authenticated.
- **One binary, one socket, zero state.** Agents are stateless; identity derives from the
  host machine-id fingerprint.
- **Beautiful on purpose.** A hand-built design system, CSS-only animations, dark-first.

## Repository layout

```
hub/       Python 3.13 · FastAPI · SQLAlchemy 2 · Alembic · uv
agent/     Go · gopsutil · coder/websocket
frontend/  Vue 3 · Vite · TypeScript · Pinia · Tailwind 4 · Storybook
docker/    Multi-arch Dockerfiles (amd64 + arm64)
examples/  docker-compose examples, k8s RBAC
docs/      Architecture, protocol, roadmap
```

## Development

```sh
# Hub
cd hub && uv sync && uv run uvicorn app.asgi:app --reload

# Agent (requires Go, or use the Docker builder)
cd agent && go run ./cmd/bifrost-agent

# Frontend
cd frontend && npm install && npm run dev
```

## License

MIT
