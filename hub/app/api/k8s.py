import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    K8sCluster,
    K8sCronJob,
    K8sIngress,
    K8sJobRun,
    K8sPod,
    K8sService,
    K8sWorkload,
)

router = APIRouter(prefix="/k8s")


def _cluster_to_dict(cluster: K8sCluster) -> dict:
    # Credentials never leave the hub.
    return {
        "id": cluster.id,
        "name": cluster.name,
        "source": cluster.source,
        "auth_mode": cluster.auth_mode,
        "api_url": cluster.api_url,
        "has_credentials": bool(
            cluster.kubeconfig_content or cluster.kubeconfig_path or cluster.token
        ),
        "insecure_skip_verify": cluster.insecure_skip_verify,
        "enabled": cluster.enabled,
        "status": cluster.status,
        "last_sync": cluster.last_sync,
    }


def _refresh_manager(request: Request) -> None:
    manager = getattr(request.app.state, "k8s_manager", None)
    if manager is not None:
        manager.request_refresh()


@router.get("/clusters")
def list_clusters(session: Session = Depends(get_session)) -> list[dict]:
    return [
        _cluster_to_dict(c)
        for c in session.scalars(select(K8sCluster).order_by(K8sCluster.name))
    ]


class ClusterCreate(BaseModel):
    name: str
    api_url: str
    token: str | None = None
    ca_pem: str | None = None
    insecure_skip_verify: bool = False


@router.post("/clusters", status_code=201)
def create_cluster(
    body: ClusterCreate, request: Request, session: Session = Depends(get_session)
) -> dict:
    cluster = K8sCluster(
        name=body.name,
        source="manual",
        auth_mode="token",
        api_url=body.api_url,
        token=body.token,
        ca_pem=body.ca_pem,
        insecure_skip_verify=body.insecure_skip_verify,
    )
    session.add(cluster)
    session.flush()
    _refresh_manager(request)
    return _cluster_to_dict(cluster)


class ClusterPatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    insecure_skip_verify: bool | None = None
    token: str | None = None


@router.patch("/clusters/{cluster_id}")
def patch_cluster(
    cluster_id: int,
    body: ClusterPatch,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    cluster = session.get(K8sCluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="cluster not found")
    for field in ("name", "enabled", "insecure_skip_verify", "token"):
        value = getattr(body, field)
        if value is not None:
            setattr(cluster, field, value)
    session.flush()
    _refresh_manager(request)
    return _cluster_to_dict(cluster)


@router.delete("/clusters/{cluster_id}", status_code=204)
def delete_cluster(
    cluster_id: int, request: Request, session: Session = Depends(get_session)
) -> None:
    cluster = session.get(K8sCluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="cluster not found")
    session.delete(cluster)
    _refresh_manager(request)


# Namespaces whose workloads stay off the services dashboard unless they
# carry explicit bifrost.* meta — nobody wants coredns as a "service".
# Plumbing namespaces: workloads here are infrastructure (GitOps, PKI), not
# services — hidden from the dashboard unless they carry explicit bifrost.*
# meta to opt back in.
SYSTEM_NAMESPACES = {"kube-system", "kube-public", "kube-node-lease", "argocd", "cert-manager"}


def _ingress_urls(session: Session) -> dict[tuple[int, str], list[tuple[set[str], str]]]:
    """(cluster, namespace) → [(match names, url)] from synced ingresses."""
    lookup: dict[tuple[int, str], list[tuple[set[str], str]]] = {}
    for ingress in session.scalars(select(K8sIngress)):
        hosts = json.loads(ingress.hosts_json or "[]")
        if not hosts:
            continue
        scheme = "https" if ingress.tls else "http"
        names = set(json.loads(ingress.backends_json or "[]"))
        names.add(ingress.name)
        lookup.setdefault((ingress.cluster_id, ingress.namespace), []).append(
            (names, f"{scheme}://{hosts[0]}")
        )
    return lookup


def k8s_services_list(session: Session) -> list[dict]:
    """Workloads shaped like dashboard services (ContainerInfo-compatible).

    One card per *app*: deployments only — statefulsets/daemonsets are
    plumbing unless they carry explicit bifrost.* meta. The URL falls out of
    the workload's ingress (backend service or ingress named like it), with
    the bifrost.url annotation as override."""
    from app.ingest.handlers import merge_override
    from app.models import ServiceOverride

    rows = session.execute(
        select(K8sWorkload, K8sCluster)
        .join(K8sCluster, K8sWorkload.cluster_id == K8sCluster.id)
        .order_by(K8sCluster.name, K8sWorkload.namespace, K8sWorkload.name)
    ).all()
    ingresses = _ingress_urls(session)
    overrides = {
        (o.cluster_id, o.container_name): o
        for o in session.scalars(
            select(ServiceOverride).where(ServiceOverride.cluster_id.is_not(None))
        )
    }
    services = []
    for workload, cluster in rows:
        meta = json.loads(workload.meta_json or "{}")
        if workload.namespace in SYSTEM_NAMESPACES and not meta:
            continue
        if workload.kind != "deployment" and not meta:
            continue
        if "url" not in meta:
            for names, url in ingresses.get((cluster.id, workload.namespace), []):
                if workload.name in names:
                    meta["url"] = url
                    break
        meta = merge_override(
            meta,
            overrides.get(
                (cluster.id, f"{workload.kind}:{workload.namespace}:{workload.name}")
            ),
        )
        desired = workload.replicas_desired or 0
        ready = workload.replicas_ready or 0
        if desired == 0:
            state, health = "paused", None
        elif ready >= desired:
            state, health = "running", None
        else:
            state, health = "running", "unhealthy"
        images = json.loads(workload.images_json or "[]")
        services.append(
            {
                "id": f"k8s:{cluster.id}:{workload.kind}:{workload.namespace}:{workload.name}",
                "name": workload.name,
                "image": images[0] if images else None,
                "state": state,
                "health": health,
                "ports": [],
                "meta": meta,
                "started_at": None,
                "cpu_millis": workload.cpu_millis,
                "mem_bytes": workload.mem_bytes,
                "updated_at": workload.updated_at,
                "node_uuid": f"k8s:{cluster.id}",
                "node_name": cluster.name,
                "source": "k8s",
            }
        )
    return services


@router.get("/workloads")
def list_workloads(session: Session = Depends(get_session)) -> list[dict]:
    return [
        {
            "cluster_id": w.cluster_id,
            "kind": w.kind,
            "namespace": w.namespace,
            "name": w.name,
            "replicas_desired": w.replicas_desired,
            "replicas_ready": w.replicas_ready,
            "images": json.loads(w.images_json or "[]"),
        }
        for w in session.scalars(
            select(K8sWorkload).order_by(K8sWorkload.namespace, K8sWorkload.name)
        )
    ]


@router.get("/pods")
def list_pods(session: Session = Depends(get_session)) -> list[dict]:
    return [
        {
            "cluster_id": p.cluster_id,
            "namespace": p.namespace,
            "name": p.name,
            "phase": p.phase,
            "ready": p.ready,
            "restarts": p.restarts,
            "node_name": p.node_name,
        }
        for p in session.scalars(select(K8sPod).order_by(K8sPod.namespace, K8sPod.name))
    ]


@router.get("/services")
def list_services(session: Session = Depends(get_session)) -> list[dict]:
    return [
        {
            "cluster_id": s.cluster_id,
            "namespace": s.namespace,
            "name": s.name,
            "type": s.type,
            "cluster_ip": s.cluster_ip,
            "ports": json.loads(s.ports_json or "[]"),
        }
        for s in session.scalars(
            select(K8sService).order_by(K8sService.namespace, K8sService.name)
        )
    ]


@router.get("/ingresses")
def list_ingresses(session: Session = Depends(get_session)) -> list[dict]:
    return [
        {
            "cluster_id": i.cluster_id,
            "namespace": i.namespace,
            "name": i.name,
            "hosts": json.loads(i.hosts_json or "[]"),
            "tls": i.tls,
        }
        for i in session.scalars(
            select(K8sIngress).order_by(K8sIngress.namespace, K8sIngress.name)
        )
    ]


@router.get("/cronjobs")
def list_cronjobs(session: Session = Depends(get_session)) -> list[dict]:
    return [
        {
            "id": c.id,
            "cluster_id": c.cluster_id,
            "namespace": c.namespace,
            "name": c.name,
            "schedule": c.schedule,
            "suspended": c.suspended,
            "last_run_ts": c.last_run_ts,
            "last_result": c.last_result,
            "last_duration_s": c.last_duration_s,
        }
        for c in session.scalars(
            select(K8sCronJob).order_by(K8sCronJob.namespace, K8sCronJob.name)
        )
    ]


@router.get("/cronjobs/{cronjob_id}/runs")
def cronjob_runs(cronjob_id: int, session: Session = Depends(get_session)) -> list[dict]:
    if session.get(K8sCronJob, cronjob_id) is None:
        raise HTTPException(status_code=404, detail="cronjob not found")
    return [
        {
            "job_name": r.job_name,
            "started_ts": r.started_ts,
            "finished_ts": r.finished_ts,
            "succeeded": r.succeeded,
            "duration_s": r.duration_s,
            "failure_reason": r.failure_reason,
        }
        for r in session.scalars(
            select(K8sJobRun)
            .where(K8sJobRun.cronjob_id == cronjob_id)
            .order_by(K8sJobRun.finished_ts.desc())
        )
    ]
