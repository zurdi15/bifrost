# Kubernetes integration (phase 5 — design)

Multi-cluster is first class: today one k3s on a minipc, tomorrow another cluster on any
node — with no manual configuration.

## Autodiscovery

The agent checks its node for cluster markers using its read-only host rootfs mount:
kubeconfigs at `/etc/rancher/k3s/k3s.yaml` (k3s), `/etc/kubernetes/admin.conf` (kubeadm),
`/var/lib/k0s/pki/admin.conf` (k0s), plus port 6443 listening. It reports `k8s_detected`
with distro, version, API endpoint and — when readable — the kubeconfig content.

The hub then creates the cluster as *discovered*: if a kubeconfig arrived, it rewrites
`server: https://127.0.0.1:6443` to the node address seen on the agent's WebSocket
connection and starts watching immediately. Otherwise the UI shows "cluster detected on
<node> — add credentials". If TLS verification fails because the reachable IP is not in
the API server cert SANs (typical with Tailscale IPs), the UI explains k3s `tls-san` and
offers a per-cluster `insecure_skip_verify` toggle.

## Watching

The hub — never the agents — watches each cluster: a thin httpx client using streaming
`?watch=true` with `resourceVersion` resume and a full relist every 5min. One watcher per
cluster; clusters with no agent can be added manually (mounted kubeconfig or
url + token + ca).

Watched resources: nodes, namespaces, pods, services, events; apps/: deployments,
daemonsets, statefulsets; batch/: **cronjobs, jobs** (Job completions are recorded as
`k8s_job_runs` — success, duration, failure reason — which is exactly the backup-cronjob
monitoring case); networking.k8s.io/: ingresses.

## RBAC

[examples/k8s/rbac.yaml](../examples/k8s/rbac.yaml): `ServiceAccount bifrost-viewer` +
ClusterRole with `get,list,watch` only, and a long-lived token Secret. No write verbs.
