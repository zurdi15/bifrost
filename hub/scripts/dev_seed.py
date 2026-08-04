"""Seed a local dev hub with lifelike fixtures — never point this at a real one.

Bookmarks, widgets and a monitored endpoint go in through the public REST API.
Docker-style nodes are played by fake agents speaking the real WebSocket
protocol (hello → containers/fs/smart → metrics + heartbeats), so the hub sees
them as genuinely online: live gauges, streaming sparklines, container stats.
One node drops on purpose after ~25 s to demo the offline flatline. Kubernetes
rows (workloads, cronjobs, job runs) are written straight to the state DB as a
disabled cluster so the watcher never tries to reach it.

Usage (dev.sh --seed does this for you):
    cd hub && uv run python scripts/dev_seed.py [--hub http://localhost:8000]

Runs until Ctrl-C, keeping the fake agents alive.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ENROLL_TOKEN = os.environ.get("BIFROST_ENROLL_TOKEN", "change-me")
DEFAULT_DATA_DIR = str(Path(__file__).resolve().parent.parent.parent / "data")

# ── fixture data ─────────────────────────────────────────────────────────────

BOOKMARKS = [
    {"name": "grafana", "url": "http://localhost:3000", "group": "observability"},
    {"name": "prometheus", "url": "http://localhost:9090", "group": "observability"},
    {"name": "gitea", "url": "http://localhost:3001", "group": "forge"},
    {"name": "woodpecker", "url": "http://localhost:8001", "group": "forge"},
    {"name": "wiki", "url": "http://localhost:3002", "group": ""},
]

WIDGETS = [
    {"type": "weather", "title": None, "config": {"lat": 40.42, "lon": -3.7}},
    {"type": "clock", "title": None, "config": {}},
]


def _containers(
    specs: list[tuple[str, str, str, str, dict[str, str], list[str]]],
) -> list[dict]:
    rows = []
    for name, image, state, health, labels, ports in specs:
        rows.append(
            {
                "container_id": hashlib.sha256(name.encode()).hexdigest()[:12],
                "name": name,
                "image": image,
                "state": state,
                "health": health,
                "ports": ports,
                "labels": labels,
                "started_at": int(time.time()) - random.randint(3600, 400_000),
            }
        )
    return rows


# Ports/labels are picked to exercise every gateway rule: derived routes,
# an explicit bifrost.url, bifrost.path, bifrost.port disambiguation,
# ambiguous ports, and honest no-port exclusions.
JOTUN_CONTAINERS = _containers(
    [
        ("jellyfin", "linuxserver/jellyfin:10.9", "running", "healthy",
         {"bifrost.group": "media"}, ["8096:8096/tcp"]),
        ("sonarr", "linuxserver/sonarr:4.0", "running", "",
         {"bifrost.group": "media"}, ["8989:8989/tcp"]),
        ("radarr", "linuxserver/radarr:5.7", "running", "",
         {"bifrost.group": "media", "bifrost.url": "https://movies.example.net"},
         ["7878:7878/tcp"]),
        ("pihole", "pihole/pihole:2026.02.0", "running", "healthy",
         {"bifrost.group": "network", "bifrost.path": "/admin"}, ["8053:80/tcp"]),
        ("unbound", "alpinelinux/unbound:latest", "running", "",
         {"bifrost.group": "network"}, ["53/udp"]),
        ("caddy", "caddy:2.8", "running", "", {}, ["80:80/tcp", "443:443/tcp"]),
        ("postgres", "postgres:17-alpine", "running", "unhealthy", {}, []),
        ("backup-runner", "restic/restic:0.17", "exited", "",
         {"bifrost.hide": "true"}, []),
    ]
)

VANAHEIM_CONTAINERS = _containers(
    [
        ("syncthing", "syncthing/syncthing:1.27", "running", "healthy",
         {"bifrost.group": "storage"}, ["8384:8384/tcp"]),
        ("minio", "minio/minio:latest", "running", "",
         {"bifrost.group": "storage", "bifrost.port": "9001"},
         ["9000:9000/tcp", "9001:9001/tcp"]),
        ("scrutiny", "analogj/scrutiny:latest", "running", "", {}, []),
    ]
)

JOTUN_MOUNTS = [
    {"mountpoint": "/", "device": "/dev/nvme0n1p2", "fstype": "ext4",
     "total_bytes": 512 * 2**30, "used_bytes": 210 * 2**30, "stale": False},
    {"mountpoint": "/var/lib/docker", "device": "/dev/nvme0n1p3", "fstype": "ext4",
     "total_bytes": 256 * 2**30, "used_bytes": 97 * 2**30, "stale": False},
]

VANAHEIM_MOUNTS = [
    {"mountpoint": "/", "device": "/dev/sda1", "fstype": "ext4",
     "total_bytes": 64 * 2**30, "used_bytes": 21 * 2**30, "stale": False},
    {"mountpoint": "/srv/pool", "device": "/dev/md0", "fstype": "btrfs",
     "total_bytes": 16 * 2**40, "used_bytes": 11 * 2**40, "stale": False},
    {"mountpoint": "/mnt/offsite", "device": "peer:/backups", "fstype": "nfs",
     "total_bytes": 8 * 2**40, "used_bytes": 5 * 2**40, "stale": True},
]

JOTUN_DISKS = [
    {"device": "/dev/nvme0n1", "model": "Samsung SSD 990 PRO 1TB", "serial": "S6Z1NX0W",
     "kind": "nvme", "capacity_bytes": 2**40, "smart_status": "passed", "temp_c": 42.0,
     "power_on_hours": 6100, "wear_pct": 3.0},
]

VANAHEIM_DISKS = [
    {"device": "/dev/sda", "model": "WDC WD80EFAX", "serial": "VGH1A001", "kind": "hdd",
     "capacity_bytes": 8 * 10**12, "smart_status": "passed", "temp_c": 37.0,
     "power_on_hours": 21500, "realloc_sectors": 0, "pending_sectors": 0},
    {"device": "/dev/sdb", "model": "WDC WD80EFAX", "serial": "VGH1A002", "kind": "hdd",
     "capacity_bytes": 8 * 10**12, "smart_status": "passed", "temp_c": 38.5,
     "power_on_hours": 21480, "realloc_sectors": 0, "pending_sectors": 0},
    {"device": "/dev/sdc", "model": "ST8000VN004", "serial": "ZM402XyZ", "kind": "hdd",
     "capacity_bytes": 8 * 10**12, "smart_status": "passed", "temp_c": 41.0,
     "power_on_hours": 43800, "realloc_sectors": 4, "pending_sectors": 8},
    {"device": "/dev/sdd", "model": "ST4000DM004", "serial": "WFN0KHH0", "kind": "hdd",
     "capacity_bytes": 4 * 10**12, "smart_status": "failed", "temp_c": 46.0,
     "power_on_hours": 61300, "realloc_sectors": 122, "pending_sectors": 40},
    {"device": "/dev/sde", "model": "CT1000MX500SSD1", "serial": "2151E5D8", "kind": "ssd",
     "capacity_bytes": 10**12, "smart_status": "passed", "temp_c": 33.0,
     "power_on_hours": 15300, "wear_pct": 12.0},
]

K8S_WORKLOADS = [
    # (name, images, desired, ready, meta, cpu_millis, mem_bytes)
    ("argocd-server", ["quay.io/argoproj/argocd:v2.12"], 1, 1,
     {"group": "platform", "url": "http://localhost:8082"}, 45, 310 * 2**20),
    ("grafana", ["grafana/grafana:11.1"], 1, 1,
     {"group": "observability", "url": "http://localhost:3000"}, 30, 190 * 2**20),
    ("immich-server", ["ghcr.io/immich-app/immich-server:v1.110"], 1, 1,
     {"group": "media"}, 120, 900 * 2**20),
    ("paperless", ["ghcr.io/paperless-ngx/paperless-ngx:2.11"], 1, 0,
     {"group": "platform"}, None, None),
]

K8S_CRONJOBS = [
    # (name, schedule, runs: list of (age_s, duration_s, ok))
    ("volume-backup", "0 3 * * *",
     [(86400 * n + 3600, 840 + n * 12, n != 2) for n in range(1, 6)]),
    ("db-dump", "30 2 * * *",
     [(86400 * n + 1800, 95 + n * 4, True) for n in range(1, 4)]),
]


# ── REST seeding ─────────────────────────────────────────────────────────────


async def wait_healthy(client: httpx.AsyncClient) -> None:
    for _ in range(60):
        try:
            response = await client.get("/api/v1/health")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    raise SystemExit("hub never became healthy — is dev.sh running?")


async def seed_rest(client: httpx.AsyncClient) -> None:
    existing = {b["name"] for b in (await client.get("/api/v1/bookmarks")).json()}
    for bookmark in BOOKMARKS:
        if bookmark["name"] not in existing:
            await client.post("/api/v1/bookmarks", json=bookmark)

    have_types = {w["type"] for w in (await client.get("/api/v1/widgets")).json()}
    for widget in WIDGETS:
        if widget["type"] not in have_types:
            await client.post("/api/v1/widgets", json=widget)

    # Widgets only show once they're placed in the dashboard's ambient rail.
    layout = (await client.get("/api/v1/dashboard")).json()
    if not layout.get("ambient"):
        widgets = (await client.get("/api/v1/widgets")).json()
        layout["ambient"] = [
            {"id": w["id"], "size": "2x1" if w["type"] == "weather" else "1x1"}
            for w in widgets
        ]
        await client.put("/api/v1/dashboard", json=layout)

    nodes = {n["name"] for n in (await client.get("/api/v1/nodes")).json()}
    if "heimdall" not in nodes:
        await client.post(
            "/api/v1/nodes/endpoints",
            json={
                "name": "heimdall",
                "checks": [
                    {"kind": "http", "target": "http://localhost:8000/api/v1/health",
                     "interval_s": 30, "timeout_s": 5, "expect_status": 200},
                    {"kind": "tcp", "target": "localhost:1", "interval_s": 30,
                     "timeout_s": 2},
                ],
            },
        )
    print("seeded: bookmarks, widgets, endpoint", flush=True)


# ── Kubernetes fixtures (state DB, disabled cluster) ─────────────────────────


def seed_k8s(data_dir: Path) -> None:
    os.environ.setdefault("BIFROST_DATA_DIR", str(data_dir))
    from app.db import init_engine, session_scope
    from app.models import K8sCluster, K8sCronJob, K8sJobRun, K8sWorkload, now_ts

    init_engine()
    with session_scope() as session:
        from sqlalchemy import select

        if session.scalar(select(K8sCluster).where(K8sCluster.name == "yggdrasil")):
            print("seeded: k8s (already present)", flush=True)
            return
        cluster = K8sCluster(
            name="yggdrasil", source="manual", enabled=False, status="ok",
            api_url="https://localhost:6443", last_sync=now_ts(),
        )
        session.add(cluster)
        session.flush()
        for name, images, desired, ready, meta, cpu, mem in K8S_WORKLOADS:
            session.add(
                K8sWorkload(
                    cluster_id=cluster.id, kind="deployment", namespace="apps",
                    name=name, replicas_desired=desired, replicas_ready=ready,
                    images_json=json.dumps(images), meta_json=json.dumps(meta),
                    cpu_millis=cpu, mem_bytes=mem,
                )
            )
        now = now_ts()
        for name, schedule, runs in K8S_CRONJOBS:
            cronjob = K8sCronJob(
                cluster_id=cluster.id, namespace="apps", name=name, schedule=schedule,
                last_run_ts=now - runs[0][0], last_result="ok" if runs[0][2] else "failed",
                last_duration_s=runs[0][1],
            )
            session.add(cronjob)
            session.flush()
            for index, (age_s, duration_s, ok) in enumerate(runs):
                session.add(
                    K8sJobRun(
                        cronjob_id=cronjob.id, job_name=f"{name}-{29200000 + index}",
                        started_ts=now - age_s, finished_ts=now - age_s + duration_s,
                        succeeded=ok, duration_s=duration_s,
                        failure_reason=None if ok else "BackoffLimitExceeded",
                    )
                )
    print("seeded: k8s cluster + workloads + cronjobs", flush=True)


# ── fake agents over the real protocol ───────────────────────────────────────


class FakeAgent:
    def __init__(
        self,
        name: str,
        *,
        arch: str = "amd64",
        containers: list[dict] | None = None,
        mounts: list[dict] | None = None,
        disks: list[dict] | None = None,
        cpu_base: float = 20.0,
        temp_base: float = 48.0,
        drop_after_s: float | None = None,
    ) -> None:
        self.name = name
        self.arch = arch
        self.containers = containers or []
        self.mounts = mounts or []
        self.disks = disks or []
        self.cpu_base = cpu_base
        self.temp_base = temp_base
        self.drop_after_s = drop_after_s
        self.fingerprint = hashlib.sha256(f"bifrost-dev-{name}".encode()).hexdigest()
        self.seq = 0
        self.phase = random.uniform(0, math.tau)

    def frame(self, t: str, **fields: object) -> str:
        self.seq += 1
        return json.dumps({"t": t, "seq": self.seq, "ts": int(time.time()), **fields})

    def metric_samples(self) -> list[dict]:
        wobble = math.sin(time.time() / 60 + self.phase)
        cpu = max(1.0, self.cpu_base + wobble * 12 + random.uniform(-3, 3))
        mem_total = 16 * 2**30
        mem_pct = 42 + wobble * 6 + random.uniform(-1, 1)
        samples = {
            "cpu.pct": round(cpu, 2),
            "cpu.load1": round(cpu / 25, 2),
            "cpu.load5": round(cpu / 28, 2),
            "cpu.load15": round(cpu / 30, 2),
            "mem.total": float(mem_total),
            "mem.used": round(mem_total * mem_pct / 100),
            "mem.pct": round(mem_pct, 2),
            "temp.cpu": round(self.temp_base + wobble * 5 + random.uniform(-1, 1), 1),
            "net.eth0.rx_bps": round(random.uniform(2e5, 9e6), 1),
            "net.eth0.tx_bps": round(random.uniform(1e5, 3e6), 1),
        }
        return [{"name": k, "value": v} for k, v in samples.items()]

    def container_stats(self) -> list[dict]:
        stats = []
        for container in self.containers:
            if container["state"] != "running":
                continue
            stats.append(
                {
                    "container_id": container["container_id"],
                    "cpu_pct": round(random.uniform(0.2, 14.0), 1),
                    "mem_bytes": random.randint(40, 900) * 2**20,
                    "mem_pct": round(random.uniform(0.5, 8.0), 1),
                }
            )
        return stats

    async def run(self, ws_url: str) -> None:
        started = time.monotonic()
        while True:
            try:
                await self._session(ws_url, started)
            except (OSError, websockets.WebSocketException) as exc:
                print(f"[{self.name}] connection lost ({exc}); retrying in 3s", flush=True)
                await asyncio.sleep(3)
                continue
            return  # deliberate drop: stay down

    async def _session(self, ws_url: str, started: float) -> None:
        headers = {
            "Authorization": f"Bearer {ENROLL_TOKEN}",
            "X-Bifrost-Fingerprint": self.fingerprint,
        }
        async with websockets.connect(ws_url, additional_headers=headers) as ws:
            self.seq = 0
            await ws.send(
                json.dumps(
                    {
                        "t": "hello", "proto": 1, "agent_version": "dev-seed",
                        "hostname": self.name, "os": "linux", "arch": self.arch,
                        "boot_ts": int(time.time()) - random.randint(4, 30) * 86400,
                        "caps": ["docker", "smart"], "start_seq": 0,
                    }
                )
            )
            await ws.recv()  # hello_ack
            drain = asyncio.create_task(self._drain(ws))
            try:
                await ws.send(self.frame("containers_full", containers=self.containers))
                await ws.send(self.frame("fs", mounts=self.mounts))
                if self.disks:
                    await ws.send(self.frame("smart", disks=self.disks))
                print(f"[{self.name}] online", flush=True)
                tick = 0
                while True:
                    await ws.send(self.frame("metrics", samples=self.metric_samples()))
                    if tick % 3 == 0:
                        await ws.send(self.frame("heartbeat"))
                    if self.containers:
                        await ws.send(self.frame("container_stats", stats=self.container_stats()))
                    if self.drop_after_s and time.monotonic() - started > self.drop_after_s:
                        print(f"[{self.name}] dropping on purpose (offline demo)", flush=True)
                        return
                    tick += 1
                    await asyncio.sleep(10)
            finally:
                drain.cancel()

    @staticmethod
    async def _drain(ws) -> None:  # noqa: ANN001 — acks/config, ignored
        async for _ in ws:
            pass


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", default="http://localhost:8000")
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help="hub data dir (for the k8s fixtures); dev.sh's ./data by default",
    )
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.hub, timeout=10) as client:
        await wait_healthy(client)
        await seed_rest(client)
    seed_k8s(Path(args.data_dir))

    ws_url = args.hub.replace("http", "ws", 1) + "/api/ws/agent"
    agents = [
        FakeAgent("jotun", containers=JOTUN_CONTAINERS, mounts=JOTUN_MOUNTS,
                  disks=JOTUN_DISKS, cpu_base=30.0, temp_base=55.0),
        FakeAgent("vanaheim", arch="arm64", containers=VANAHEIM_CONTAINERS,
                  mounts=VANAHEIM_MOUNTS, disks=VANAHEIM_DISKS, cpu_base=12.0,
                  temp_base=44.0),
        FakeAgent("muspell", cpu_base=55.0, temp_base=70.0, drop_after_s=25),
    ]
    print("fake agents running — Ctrl-C to stop", flush=True)
    await asyncio.gather(*(agent.run(ws_url) for agent in agents))


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
