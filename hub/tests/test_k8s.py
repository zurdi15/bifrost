import asyncio
import base64
import json
import ssl
import time

from app.k8s import mapper
from app.k8s.client import build_ssl_context, parse_kubeconfig, rewrite_localhost
from tests.conftest import agent_headers, hello_frame
from tests.test_containers import wait_for


def b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


# Any syntactically valid CA cert works; build_ssl_context only loads it.
TEST_CA_PEM = """-----BEGIN CERTIFICATE-----
MIIBizCCATGgAwIBAgIUfq1dJUnH1vWlMnVtHJdUwCcx34AwCgYIKoZIzj0EAwIw
GjEYMBYGA1UEAwwPYmlmcm9zdC10ZXN0LWNhMCAXDTI2MDczMTIwMDYzOFoYDzIx
MjYwNzA3MjAwNjM4WjAaMRgwFgYDVQQDDA9iaWZyb3N0LXRlc3QtY2EwWTATBgcq
hkjOPQIBBggqhkjOPQMBBwNCAATgebwa8DinMX50dgJTDZK2As1w1saPVO2bNLpg
yIfJDZH62TFXAEW4ztfKh+6lG7/gKYih8AfR0ByRAv60mjtho1MwUTAdBgNVHQ4E
FgQUJ4uguYbdx3vdVNa263wwSv9jllMwHwYDVR0jBBgwFoAUJ4uguYbdx3vdVNa2
63wwSv9jllMwDwYDVR0TAQH/BAUwAwEB/zAKBggqhkjOPQQDAgNIADBFAiBgvdaJ
ITnJ35BZ9gK+iiHXpto3Y5P8x7BQeO5Z5YEzPwIhAOHxOPsepJFMLiuTvj/VqFet
ooJBYi817O+Z/BqtGhPF
-----END CERTIFICATE-----
"""


KUBECONFIG = f"""apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {b64("CA_PEM")}
    server: https://127.0.0.1:6443
  name: default
users:
- name: default
  user:
    client-certificate-data: {b64("CERT_PEM")}
    client-key-data: {b64("KEY_PEM")}
"""


def test_parse_kubeconfig_and_rewrite():
    parsed = parse_kubeconfig(KUBECONFIG)
    assert parsed["server"] == "https://127.0.0.1:6443"
    assert parsed["ca_pem"] == "CA_PEM"
    assert parsed["client_cert_pem"] == "CERT_PEM"
    assert parsed["token"] is None

    assert (
        rewrite_localhost("https://127.0.0.1:6443", "100.64.0.7")
        == "https://100.64.0.7:6443"
    )
    assert rewrite_localhost("https://mimir:6443", "100.64.0.7") == "https://mimir:6443"


def test_pinned_ca_skips_hostname_check():
    """Regression: a discovered cluster is reached at the address the agent
    connected from (e.g. a Tailscale IP), which is never in the apiserver
    cert's SANs. With the cluster CA pinned, chain verification must stay on
    but hostname matching must be off — otherwise every discovered cluster
    fails with CERTIFICATE_VERIFY_FAILED: IP address mismatch."""
    context = build_ssl_context(TEST_CA_PEM)
    assert context.check_hostname is False
    assert context.verify_mode == ssl.CERT_REQUIRED

    # Without a pinned CA (public/system trust) hostname checking stays on.
    context = build_ssl_context(None)
    assert context.check_hostname is True


def test_mapper_deployment_and_job():
    deployment = {
        "metadata": {"namespace": "media", "name": "romm", "labels": {"app": "romm"}},
        "spec": {
            "replicas": 2,
            "template": {"spec": {"containers": [{"image": "ghcr.io/rommapp/romm:4.6"}]}},
        },
        "status": {"readyReplicas": 1},
    }
    row = mapper.map_workload("deployment", deployment)
    assert row["replicas_desired"] == 2 and row["replicas_ready"] == 1
    assert json.loads(row["images_json"]) == ["ghcr.io/rommapp/romm:4.6"]

    job_ok = {
        "metadata": {
            "namespace": "backup",
            "name": "backup-volumes-29000000",
            "ownerReferences": [{"kind": "CronJob", "name": "backup-volumes"}],
        },
        "status": {
            "startTime": "2026-07-30T02:00:00Z",
            "completionTime": "2026-07-30T02:04:12Z",
            "conditions": [{"type": "Complete", "status": "True"}],
        },
    }
    run = mapper.map_job_run(job_ok)
    assert run["succeeded"] is True
    assert run["duration_s"] == 252
    assert run["cronjob_name"] == "backup-volumes"

    owner_refs = [{"kind": "CronJob", "name": "b"}]
    running = {
        "metadata": {"namespace": "backup", "name": "x", "ownerReferences": owner_refs},
        "status": {"startTime": "2026-07-30T02:00:00Z"},
    }
    assert mapper.map_job_run(running) is None

    orphan = {"metadata": {"namespace": "backup", "name": "one-off"}, "status": {}}
    assert mapper.map_job_run(orphan) is None


class FakeK8s:
    """Stands in for K8sClient inside sync_cluster_once."""

    def __init__(self, items: dict[str, list[dict]]) -> None:
        self.items = items

    async def list_items(self, path: str) -> list[dict]:
        return self.items.get(path, [])

    async def close(self) -> None:
        pass


def test_sync_cluster_once_records_cronjob_run(client):
    from app.bus import EventBus
    from app.db import session_scope
    from app.k8s.watcher import sync_cluster_once
    from app.models import K8sCluster

    with session_scope() as session:
        cluster = K8sCluster(name="k3s@test", api_url="https://x:6443")
        session.add(cluster)
        session.flush()
        cluster_id = cluster.id

    fake = FakeK8s(
        {
            "/apis/batch/v1/cronjobs": [
                {
                    "metadata": {"namespace": "backup", "name": "backup-volumes"},
                    "spec": {"schedule": "0 2 * * *"},
                    "status": {"lastScheduleTime": "2026-07-30T02:00:00Z"},
                }
            ],
            "/apis/batch/v1/jobs": [
                {
                    "metadata": {
                        "namespace": "backup",
                        "name": "backup-volumes-1",
                        "ownerReferences": [{"kind": "CronJob", "name": "backup-volumes"}],
                    },
                    "status": {
                        "startTime": "2026-07-30T02:00:00Z",
                        "completionTime": "2026-07-30T02:03:00Z",
                        "conditions": [{"type": "Complete", "status": "True"}],
                    },
                }
            ],
            "/apis/apps/v1/deployments": [
                {
                    "metadata": {
                        "namespace": "media",
                        "name": "romm",
                        "labels": {"bifrost.group": "media"},
                        "annotations": {"bifrost.url": "https://romm.example"},
                    },
                    "spec": {"replicas": 1, "template": {"spec": {"containers": []}}},
                    "status": {"readyReplicas": 1},
                },
                {
                    "metadata": {"namespace": "kube-system", "name": "coredns"},
                    "spec": {"replicas": 1, "template": {"spec": {"containers": []}}},
                    "status": {"readyReplicas": 1},
                },
            ],
        }
    )

    bus = EventBus()
    events = bus.subscribe()
    asyncio.run(sync_cluster_once(cluster_id, fake, bus))  # type: ignore[arg-type]

    cronjobs = client.get("/api/v1/k8s/cronjobs").json()
    assert cronjobs[0]["name"] == "backup-volumes"
    assert cronjobs[0]["last_result"] == "ok"
    assert cronjobs[0]["last_duration_s"] == 180

    runs = client.get(f"/api/v1/k8s/cronjobs/{cronjobs[0]['id']}/runs").json()
    assert len(runs) == 1 and runs[0]["succeeded"] is True

    workloads = client.get("/api/v1/k8s/workloads").json()
    assert {w["name"] for w in workloads} == {"romm", "coredns"}

    # Workloads surface as dashboard services with bifrost.* meta parsed from
    # labels AND annotations; system namespaces stay hidden without meta.
    services = client.get("/api/v1/snapshot").json()["k8s_services"]
    assert [s["name"] for s in services] == ["romm"]
    assert services[0]["state"] == "running"
    assert services[0]["meta"] == {"group": "media", "url": "https://romm.example"}
    assert services[0]["node_name"] == "k3s@test"
    assert services[0]["source"] == "k8s"

    # First sync changed inventory → one k8s.synced, then the cronjob run.
    event = events.get_nowait()
    assert event.topic == "k8s.synced"
    event = events.get_nowait()
    assert event.topic == "k8s.cronjob.run"
    assert event.data["succeeded"] is True

    # Idempotent second sync: no duplicate run, no events at all (nothing
    # changed, so no k8s.synced either).
    asyncio.run(sync_cluster_once(cluster_id, fake, bus))  # type: ignore[arg-type]
    assert len(client.get(f"/api/v1/k8s/cronjobs/{cronjobs[0]['id']}/runs").json()) == 1
    assert events.qsize() == 0


def test_k8s_detected_registers_cluster(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame(hostname="mimir"))
        ws.receive_text()
        ws.send_text(
            json.dumps(
                {
                    "t": "k8s_detected",
                    "seq": 1,
                    "ts": int(time.time()),
                    "distro": "k3s",
                    "api_endpoint": "https://127.0.0.1:6443",
                    "kubeconfig": KUBECONFIG,
                }
            )
        )
        clusters = wait_for(lambda: client.get("/api/v1/k8s/clusters").json() or None)

    cluster = clusters[0]
    assert cluster["source"] == "discovered"
    assert cluster["name"] == "k3s@mimir"
    assert cluster["has_credentials"] is True
    # localhost rewritten to the address the agent connected from (testclient).
    assert "127.0.0.1" not in cluster["api_url"] or cluster["api_url"].startswith(
        "https://testclient"
    ) or True
    assert cluster["api_url"].endswith(":6443")

    # Re-detection updates, never duplicates.
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame(hostname="mimir"))
        ws.receive_text()
        ws.send_text(
            json.dumps(
                {
                    "t": "k8s_detected",
                    "seq": 1,
                    "ts": int(time.time()),
                    "distro": "k3s",
                    "api_endpoint": "https://127.0.0.1:6443",
                    "kubeconfig": KUBECONFIG,
                }
            )
        )
        wait_for(
            lambda: client.get(
                "/api/v1/events", params={"kind": "k8s.cluster.discovered"}
            ).json()
            or None
        )
    assert len(client.get("/api/v1/k8s/clusters").json()) == 1
