# Bifrost — agent instructions

Self-hosted homelab dashboard. Two artifacts, both Docker-only: `bifrost-hub` (FastAPI +
SQLite + Vue SPA) and `bifrost-agent` (Go static binary). Agents push to the hub over an
outbound WebSocket. Full architecture: [docs/architecture.md](docs/architecture.md),
protocol: [docs/protocol.md](docs/protocol.md), roadmap: [docs/roadmap.md](docs/roadmap.md).

## Ground rules

- **Infrastructure-agnostic.** Never hardcode anything about a specific homelab (node names,
  IPs, Tailscale). The reference deployment lives only in `examples/`.
- **No UI auth, ever.** The dashboard is open by design (network-layer protection). Only
  agents authenticate (enroll token → per-agent token, stored as sha256).
- **The protocol contract lives in `hub/app/ingest/protocol.py`** (Pydantic). The Go mirror
  is `agent/internal/protocol/`. Change both together; bump `PROTO_VERSION` on breaking
  changes (additive fields don't bump).
- **SQLite discipline.** `bifrost.db` = state/config, migrated with Alembic. `metrics.db` =
  time series, schema via `PRAGMA user_version` in code, single batched writer — never write
  to it from request handlers.
- **All state changes go through the EventBus** (`hub/app/bus.py`) — that's what feeds the
  UI WebSocket, the `events` table, and future alerting.

## Frontend rules

- Design tokens: `frontend/src/tokens/index.ts` is the source of truth →
  `npm run build:tokens` generates `src/styles/tokens.css` (never edit the generated file).
  `npm run guard:tokens` enforces: no hex colors, no raw cubic-bezier, no `text-[..px]`
  outside the tokens; `var(--bf-aurora)` only inside `src/lib/` and `src/layouts/`.
- Animations: CSS only (no GSAP/framer-motion/auto-animate). Only `transform`/`opacity`
  (+ SVG stroke). Animate entrances, never exits. The single `prefers-reduced-motion` guard
  lives in `src/styles/animations.css`.
- Dark mode by variable redefinition, never Tailwind `dark:` variants.
- Every metric value renders in mono with `tabular-nums`.

## Commands

```sh
cd hub && uv sync && uv run pytest                  # hub tests
cd hub && uv run uvicorn app.asgi:app --reload      # hub dev server (port 8000)
cd frontend && npm run dev                          # SPA dev (proxies /api to :8000)
cd frontend && npm run test && npm run typecheck    # vitest + vue-tsc
cd frontend && npm run storybook                    # design system catalog
docker run --rm -v $PWD/agent:/src -w /src golang:1.23-alpine go test ./...   # agent tests (no local Go)
```
