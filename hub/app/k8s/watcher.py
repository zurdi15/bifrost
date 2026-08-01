"""Per-cluster inventory sync.

One asyncio task per enabled cluster polls the API every SYNC_INTERVAL_S and
reconciles the inventory tables. Polling (instead of streaming watches) keeps
the client trivial and is plenty for a homelab; a resourceVersion-resuming
watch is a documented roadmap optimization.
"""

import asyncio
import contextlib
import logging

from sqlalchemy import delete, select

from app.bus import EventBus
from app.config import settings
from app.db import session_scope
from app.k8s import mapper
from app.k8s.client import K8sClient
from app.models import (
    K8sCluster,
    K8sCronJob,
    K8sIngress,
    K8sJobRun,
    K8sPod,
    K8sService,
    K8sWorkload,
    now_ts,
)

logger = logging.getLogger("bifrost.k8s")

SYNC_INTERVAL_S = 30
JOB_RUNS_KEPT_PER_CRONJOB = 50

WORKLOAD_PATHS = {
    "deployment": "/apis/apps/v1/deployments",
    "daemonset": "/apis/apps/v1/daemonsets",
    "statefulset": "/apis/apps/v1/statefulsets",
}


def _sync_table(
    session, model, cluster_id: int, rows: list[dict], keys: tuple[str, ...]  # noqa: ANN001
) -> bool:
    """Reconcile one inventory table. Returns whether anything changed, so the
    caller can tell the UI without spamming an event every sync cycle."""
    existing = {
        tuple(getattr(row, k) for k in keys): row
        for row in session.scalars(select(model).where(model.cluster_id == cluster_id))
    }
    seen = set()
    ts = now_ts()
    changed = False
    for data in rows:
        key = tuple(data[k] for k in keys)
        seen.add(key)
        row = existing.get(key)
        if row is None:
            row = model(cluster_id=cluster_id)
            session.add(row)
            changed = True
        for field, value in data.items():
            if getattr(row, field, None) != value:
                setattr(row, field, value)
                changed = True
        if hasattr(row, "updated_at"):
            row.updated_at = ts
    for key, row in existing.items():
        if key not in seen:
            session.delete(row)
            changed = True
    return changed


async def sync_cluster_once(cluster_id: int, client: K8sClient, bus: EventBus) -> None:
    """One full inventory pull + reconcile. Raises on API errors."""
    workloads = []
    for kind, path in WORKLOAD_PATHS.items():
        for obj in await client.list_items(path):
            workloads.append(mapper.map_workload(kind, obj))
    pods = [mapper.map_pod(o) for o in await client.list_items("/api/v1/pods")]

    # Live usage via metrics-server; clusters without it just skip stats.
    pod_usage: dict[tuple[str, str], tuple[int, int]] = {}
    try:
        for obj in await client.list_items("/apis/metrics.k8s.io/v1beta1/pods"):
            namespace, name, cpu, mem = mapper.map_pod_metrics(obj)
            pod_usage[(namespace, name)] = (cpu, mem)
    except Exception:  # noqa: BLE001 — 404/403 without metrics-server
        pod_usage = {}
    workload_usage: dict[tuple[str, str, str], list[int]] = {}
    for pod in pods:
        target = mapper.workload_of_pod(pod)
        usage = pod_usage.get((pod["namespace"], pod["name"]))
        if target is None or usage is None:
            continue
        totals = workload_usage.setdefault(target, [0, 0])
        totals[0] += usage[0]
        totals[1] += usage[1]
    for workload in workloads:
        totals = workload_usage.get(
            (workload["kind"], workload["namespace"], workload["name"])
        )
        workload["cpu_millis"] = totals[0] if totals else None
        workload["mem_bytes"] = totals[1] if totals else None
    services = [mapper.map_service(o) for o in await client.list_items("/api/v1/services")]
    ingresses = [
        mapper.map_ingress(o)
        for o in await client.list_items("/apis/networking.k8s.io/v1/ingresses")
    ]
    cronjobs = [mapper.map_cronjob(o) for o in await client.list_items("/apis/batch/v1/cronjobs")]
    job_runs = [
        run
        for o in await client.list_items("/apis/batch/v1/jobs")
        if (run := mapper.map_job_run(o)) is not None
    ]

    new_runs: list[dict] = []
    inventory_changed = False
    with session_scope() as session:
        for model, rows, keys in (
            (K8sWorkload, workloads, ("kind", "namespace", "name")),
            (K8sPod, pods, ("namespace", "name")),
            (K8sService, services, ("namespace", "name")),
            (K8sIngress, ingresses, ("namespace", "name")),
            (K8sCronJob, cronjobs, ("namespace", "name")),
        ):
            if _sync_table(session, model, cluster_id, rows, keys):
                inventory_changed = True
        session.flush()

        cronjob_rows = {
            (c.namespace, c.name): c
            for c in session.scalars(
                select(K8sCronJob).where(K8sCronJob.cluster_id == cluster_id)
            )
        }
        for run in job_runs:
            cronjob = cronjob_rows.get((run["namespace"], run["cronjob_name"]))
            if cronjob is None:
                continue
            exists = session.scalar(
                select(K8sJobRun).where(
                    K8sJobRun.cronjob_id == cronjob.id,
                    K8sJobRun.job_name == run["job_name"],
                )
            )
            if exists is not None:
                continue
            session.add(
                K8sJobRun(
                    cronjob_id=cronjob.id,
                    job_name=run["job_name"],
                    started_ts=run["started_ts"],
                    finished_ts=run["finished_ts"],
                    succeeded=run["succeeded"],
                    duration_s=run["duration_s"],
                    failure_reason=run["failure_reason"],
                )
            )
            cronjob.last_result = "ok" if run["succeeded"] else "failed"
            cronjob.last_duration_s = run["duration_s"]
            # last_run_ts stays owned by the mapper (lastScheduleTime):
            # writing finished_ts here made every following sync flip it
            # back and look like an inventory change.
            new_runs.append(
                {
                    "cluster_id": cluster_id,
                    "namespace": run["namespace"],
                    "cronjob": run["cronjob_name"],
                    "job_name": run["job_name"],
                    "succeeded": run["succeeded"],
                    "duration_s": run["duration_s"],
                    "failure_reason": run["failure_reason"],
                }
            )

        # Bound per-cronjob history.
        for cronjob in cronjob_rows.values():
            stale_ids = [
                r.id
                for r in session.scalars(
                    select(K8sJobRun)
                    .where(K8sJobRun.cronjob_id == cronjob.id)
                    .order_by(K8sJobRun.finished_ts.desc())
                ).all()[JOB_RUNS_KEPT_PER_CRONJOB:]
            ]
            if stale_ids:
                session.execute(delete(K8sJobRun).where(K8sJobRun.id.in_(stale_ids)))

        cluster = session.get(K8sCluster, cluster_id)
        if cluster is not None:
            cluster.status = "ok"
            cluster.last_sync = now_ts()

    if inventory_changed:
        bus.publish("k8s.synced", {"cluster_id": cluster_id})
    for run in new_runs:
        bus.publish("k8s.cronjob.run", run)


class K8sManager:
    """Owns one sync loop per enabled cluster; refresh() reconciles tasks
    after cluster CRUD or discovery."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._tasks: dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        await self.refresh()

    async def refresh(self) -> None:
        with session_scope() as session:
            enabled_ids = set(
                session.scalars(select(K8sCluster.id).where(K8sCluster.enabled.is_(True))).all()
            )
        for cluster_id in enabled_ids - self._tasks.keys():
            self._tasks[cluster_id] = asyncio.create_task(
                self._loop(cluster_id), name=f"k8s-sync-{cluster_id}"
            )
        for cluster_id in list(self._tasks.keys() - enabled_ids):
            self._tasks.pop(cluster_id).cancel()

    def request_refresh(self) -> None:
        asyncio.get_running_loop().create_task(self.refresh())

    async def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()

    async def _loop(self, cluster_id: int) -> None:
        while True:
            client: K8sClient | None = None
            try:
                with session_scope() as session:
                    cluster = session.get(K8sCluster, cluster_id)
                    if cluster is None:
                        return
                    client = K8sClient.from_cluster(
                        cluster, cert_dir=settings.data_dir / "k8s" / str(cluster_id)
                    )
                await sync_cluster_once(cluster_id, client, self._bus)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("cluster %s sync failed: %s", cluster_id, exc)
                with session_scope() as session:
                    cluster = session.get(K8sCluster, cluster_id)
                    if cluster is not None:
                        cluster.status = f"error: {str(exc)[:200]}"
            finally:
                if client is not None:
                    await client.close()
            await asyncio.sleep(SYNC_INTERVAL_S)
