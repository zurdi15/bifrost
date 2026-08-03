# Gateway: one URL per service, automatically

The hub and agents give you the inventory; this example gives every Docker
service a working `https://<name>.<your-domain>` URL. One reverse proxy
(Caddy) fronts the homelab, and a small sidecar (`caddy-sync`) keeps its
routes in sync with what bifrost discovers — on the hub's machine and on
every other node with an agent.

```
click on a card
     │
     ▼
https://jellyfin.example.net ──DNS──▶ gateway machine
                                          │  caddy (TLS)
                                          ├─ hand-written vhost?  → as you wrote it
                                          ├─ generated vhost?     → node:port (Docker, any machine)
                                          └─ neither?             → optional catch-all (e.g. k8s ingress)
```

## What you need

1. **A domain** with a wildcard record pointing at this machine:
   `*.example.net → <gateway ip>` (plus the apex if you want the dashboard
   there). A private IP (LAN/VPN) is fine — certs come via DNS-01, so nothing
   needs to be reachable from the internet.
2. **The hub knowing your domain** — set on the hub container:

   ```yaml
   environment:
     BIFROST_SERVICE_DOMAIN: example.net
   ```

3. **This compose** on the gateway machine:

   ```sh
   cp .env.example .env   # fill in domain, Cloudflare token, hub address
   docker compose up -d --build
   ```

That's it. No systemd units, no host packages: moving the gateway (or the
hub) to another machine is `docker compose up -d` plus one env var.

## What a service needs

| Situation               | What you write                                | Resulting URL                     |
| ----------------------- | --------------------------------------------- | --------------------------------- |
| One published TCP port  | nothing at all                                | `https://<container>.example.net` |
| Several published ports | `bifrost.port=8080` label                     | `https://<container>.example.net` |
| Custom hostname         | `bifrost.url=https://media.example.net` label | as written                        |
| Keep it unrouted        | `bifrost.expose=false` label                  | none                              |

The same metadata drives the dashboard card and the route, so a card's link
and where it lands can never disagree. Requirements per node: the agent
installed, and the gateway able to reach `node:port` (same LAN or VPN — the
sidecar resolves node names via DNS, with `NODE_ADDR_*` overrides in `.env`
for anything unusual).

## How it stays correct

- **Hand-written vhosts in the Caddyfile always win.** `caddy-sync` skips any
  hostname you declared yourself, so the generated file can never hijack your
  config. Generated hostnames also yield to k8s Ingresses the hub knows about.
- **Generated state stays out of your repo.** `bifrost.d/` lives in a volume;
  the source of truth is the labels in each service's own compose file.
- **Reloads are atomic.** The sidecar POSTs the Caddyfile to caddy's admin
  API; if the config is rejected, the previous routes file is restored and
  the running config is untouched.

## Kubernetes too?

Ingress-managed services route themselves: swap the wildcard site's final
`handle` for a proxy to the cluster's ingress controller, which routes by
Host header:

```caddyfile
	handle {
		reverse_proxy <ingress-controller-ip>:80
	}
```

Priority ends up: hand-written vhost → generated Docker route → k8s ingress —
all subdomains under the one wildcard certificate.
