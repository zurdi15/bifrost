# Agent ↔ Hub protocol (v1)

Transport: WebSocket at `ws(s)://<hub>/api/ws/agent`. One JSON object per text frame.
The canonical schema lives in `hub/app/ingest/protocol.py` (Pydantic); the Go mirror is
`agent/internal/protocol/`. Within a proto version, changes are **additive only** —
unknown fields must be ignored by both sides. The hub accepts proto `N` and `N-1`.
JSON `null` for list/map fields is treated as empty (Go marshals nil that way), and a
frame that fails to parse is skipped with a warning — never a reason to drop the
connection, since the agent would resend it from its ring forever.

## Handshake

Connection headers:

```
Authorization: Bearer <token>          # enroll token (first contact) or per-agent token
X-Bifrost-Fingerprint: <sha256 hex>    # sha256 of host /etc/machine-id (or fallback)
```

1. Agent sends `hello`:

```json
{"t":"hello","proto":1,"agent_version":"0.1.0","hostname":"nas1","os":"linux",
 "arch":"arm64","boot_ts":1753900000,"caps":["system","docker"],"start_seq":0}
```

`start_seq` is the position before the agent's oldest undelivered frame (0 on a
fresh process — agents are stateless and restart their counter). The hub takes
`min(stored last_seq, start_seq)` as its dedup position, so a restarted agent
is never silently deduplicated into the void.

2. Hub replies `hello_ack`:

```json
{"t":"hello_ack","proto":1,"node_uuid":"…","agent_token":"…",
 "config":{"metrics_interval_s":10,"smart_interval_s":1800,"fs_interval_s":60},
 "resume_from_seq":417}
```

`agent_token` is present **only** when the connection enrolled with the shared token: the
hub mints a per-agent token (DB stores its sha256) and the agent keeps it in memory. If the
agent restarts and lost it, it re-enrolls; the hub reconciles by fingerprint and rotates
the token. If the hub is configured with `auto_approve=false`, enrolling nodes are created
as `pending`, get `error{code:"pending_approval"}` and are disconnected until approved.

## Messages

All agent→hub data messages carry a monotonically increasing `seq` (per connection-lifetime
of the agent process) and a `ts` (epoch seconds).

| Direction | `t` | Payload | Cadence |
|---|---|---|---|
| a→h | `metrics` | `samples: [{name, value}]` | every `metrics_interval_s` |
| a→h | `fs` | mount snapshot, `stale` flag | every `fs_interval_s` (phase 3) |
| a→h | `containers_full` | full container list | on connect + reconcile (phase 2) |
| a→h | `container_event` | start/die/health_status | real time (phase 2) |
| a→h | `smart` | per-disk parsed smartctl | every `smart_interval_s` (phase 4) |
| a→h | `k8s_detected` | distro, api endpoint, kubeconfig? | on start + on change (phase 5) |
| a→h | `heartbeat` | `{}` | every 15s |
| h→a | `ack` | `{upto_seq}` | every ~10 data messages |
| h→a | `config` | new intervals | on change from UI |
| h→a | `resync` | `{}` — asks for full snapshots | after gap detection |
| h→a | `error` | `{code, msg}` | on protocol/auth errors |
| h→a | `bye` | `{}` | graceful shutdown |

## Reliability

The agent keeps a ring buffer of un-acked messages (~2048 frames ≈ 90min of raw metrics).
On reconnect it resends everything after `resume_from_seq` from the hub's `hello_ack`.
On overflow it drops oldest raw metrics keeping 1 of every 6 (graceful thinning to ~1min
resolution) — heartbeats and non-metric messages are never thinned.

Reconnection: exponential backoff with full jitter, base 1s, cap 60s, retry forever.

## Down detection (hub side)

- Socket close → node `offline` immediately, `node.status` event.
- Missed heartbeats (15s cadence): 2 → `degraded`, 3 → `offline`. Covers half-open TCP.

Node states: `pending | online | degraded | offline | disabled`.
