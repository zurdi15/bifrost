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
