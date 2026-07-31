# Agent deployment

The agent ships only as a Docker image (`ghcr.io/zurdi15/bifrost-agent`, amd64 + arm64).
See [examples/docker-compose.agent.yml](../examples/docker-compose.agent.yml).

## Required configuration

| Env var | Meaning |
|---|---|
| `BIFROST_AGENT_HUB_URL` | Hub base URL reachable from the node (`http://` or `https://`) |
| `BIFROST_AGENT_ENROLL_TOKEN` | Must match the hub's `BIFROST_ENROLL_TOKEN` |
| `BIFROST_AGENT_NODE_NAME` | Optional friendly name (default: the host's hostname, read from `HOST_ROOT/etc/hostname`, else `os.Hostname()` — correct under `uts: host`) |
| `BIFROST_AGENT_METRICS_INTERVAL` | Seconds between metric batches (default 10) |

## Container permissions, least → most

Base (system metrics — always):

```yaml
pid: host
uts: host   # host hostname; without it the node shows up as a container id
volumes:
  - /proc:/host/proc:ro
  - /sys:/host/sys:ro
  - /:/host/rootfs:ro
  - /etc/machine-id:/etc/machine-id:ro
environment:
  HOST_PROC: /host/proc
  HOST_SYS: /host/sys
  HOST_ROOT: /host/rootfs
```

Docker discovery (phase 2): add `- /var/run/docker.sock:/var/run/docker.sock:ro`.

SMART (phase 4): add

```yaml
cap_add: [SYS_RAWIO, SYS_ADMIN]
devices: ["/dev/sda", "/dev/sdb", "/dev/nvme0"]
```

On NAS UIs (TerraMaster TOS, Synology…) where mapping devices one by one is painful,
`privileged: true` is the documented fallback.

## Identity

`fingerprint = sha256(/etc/machine-id)` (fallback: hostname + sorted MACs). The agent keeps
no state on disk: recreate the container freely, the hub reconciles by fingerprint.
