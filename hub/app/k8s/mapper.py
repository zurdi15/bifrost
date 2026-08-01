"""Map Kubernetes API objects onto Bifrost's inventory rows."""

import json
from datetime import datetime

from app.ingest.handlers import extract_bifrost_meta


def _parse_time(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def map_workload(kind: str, obj: dict) -> dict:
    meta = obj.get("metadata", {})
    spec = obj.get("spec", {})
    status = obj.get("status", {})
    desired = spec.get("replicas")
    if kind == "daemonset":
        desired = status.get("desiredNumberScheduled")
        ready = status.get("numberReady", 0)
    else:
        ready = status.get("readyReplicas", 0)
    containers = spec.get("template", {}).get("spec", {}).get("containers", [])
    # bifrost.* meta comes from labels AND annotations (annotations win —
    # k8s label values cannot hold URLs, so bifrost.url must be one).
    labels = meta.get("labels", {})
    annotations = meta.get("annotations", {})
    return {
        "kind": kind,
        "namespace": meta.get("namespace", ""),
        "name": meta.get("name", ""),
        "replicas_desired": desired,
        "replicas_ready": ready,
        "images_json": json.dumps([c.get("image", "") for c in containers]),
        "labels_json": json.dumps(labels),
        "meta_json": json.dumps(extract_bifrost_meta({**labels, **annotations})),
    }


def map_pod(obj: dict) -> dict:
    meta = obj.get("metadata", {})
    status = obj.get("status", {})
    spec = obj.get("spec", {})
    container_statuses = status.get("containerStatuses", [])
    owners = meta.get("ownerReferences", [])
    owner = owners[0] if owners else {}
    return {
        "namespace": meta.get("namespace", ""),
        "name": meta.get("name", ""),
        "phase": status.get("phase"),
        "ready": bool(container_statuses) and all(c.get("ready") for c in container_statuses),
        "restarts": sum(c.get("restartCount", 0) for c in container_statuses),
        "node_name": spec.get("nodeName"),
        "owner_kind": owner.get("kind"),
        "owner_name": owner.get("name"),
    }


def map_service(obj: dict) -> dict:
    meta = obj.get("metadata", {})
    spec = obj.get("spec", {})
    ports = [
        f"{p.get('port')}:{p.get('targetPort', '')}/{p.get('protocol', 'TCP').lower()}"
        for p in spec.get("ports", [])
    ]
    return {
        "namespace": meta.get("namespace", ""),
        "name": meta.get("name", ""),
        "type": spec.get("type"),
        "cluster_ip": spec.get("clusterIP"),
        "ports_json": json.dumps(ports),
    }


def map_ingress(obj: dict) -> dict:
    meta = obj.get("metadata", {})
    spec = obj.get("spec", {})
    hosts = [rule.get("host", "") for rule in spec.get("rules", []) if rule.get("host")]
    # Backend service names let the dashboard link a workload to its ingress.
    backends = set()
    if name := spec.get("defaultBackend", {}).get("service", {}).get("name"):
        backends.add(name)
    for rule in spec.get("rules", []):
        for path in rule.get("http", {}).get("paths", []):
            if name := path.get("backend", {}).get("service", {}).get("name"):
                backends.add(name)
    return {
        "namespace": meta.get("namespace", ""),
        "name": meta.get("name", ""),
        "hosts_json": json.dumps(hosts),
        "tls": bool(spec.get("tls")),
        "backends_json": json.dumps(sorted(backends)),
    }


_MEM_UNITS = {
    "Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4,
    "k": 1000, "M": 1000**2, "G": 1000**3, "T": 1000**4,
}


def parse_cpu_millis(quantity: str) -> int:
    """k8s CPU quantity → millicores ('250m' → 250, '1' → 1000, '12345678n')."""
    quantity = (quantity or "").strip()
    if not quantity:
        return 0
    try:
        if quantity.endswith("n"):
            return int(int(quantity[:-1]) / 1_000_000)
        if quantity.endswith("u"):
            return int(int(quantity[:-1]) / 1_000)
        if quantity.endswith("m"):
            return int(quantity[:-1])
        return int(float(quantity) * 1000)
    except ValueError:
        return 0


def parse_mem_bytes(quantity: str) -> int:
    """k8s memory quantity → bytes ('190Mi', '1Gi', '123456k', plain bytes)."""
    quantity = (quantity or "").strip()
    if not quantity:
        return 0
    for suffix, factor in _MEM_UNITS.items():
        if quantity.endswith(suffix):
            try:
                return int(float(quantity[: -len(suffix)]) * factor)
            except ValueError:
                return 0
    try:
        return int(float(quantity))
    except ValueError:
        return 0


def map_pod_metrics(obj: dict) -> tuple[str, str, int, int]:
    """PodMetrics → (namespace, pod name, cpu millis, mem bytes)."""
    meta = obj.get("metadata", {})
    cpu = sum(
        parse_cpu_millis(c.get("usage", {}).get("cpu", ""))
        for c in obj.get("containers", [])
    )
    mem = sum(
        parse_mem_bytes(c.get("usage", {}).get("memory", ""))
        for c in obj.get("containers", [])
    )
    return meta.get("namespace", ""), meta.get("name", ""), cpu, mem


def workload_of_pod(pod: dict) -> tuple[str, str, str] | None:
    """(kind, namespace, workload name) a pod's usage rolls up to.

    Deployments own pods through a ReplicaSet named <deployment>-<hash>."""
    owner_kind, owner_name = pod.get("owner_kind"), pod.get("owner_name")
    if not owner_kind or not owner_name:
        return None
    namespace = pod.get("namespace", "")
    if owner_kind == "ReplicaSet":
        return ("deployment", namespace, owner_name.rsplit("-", 1)[0])
    if owner_kind == "StatefulSet":
        return ("statefulset", namespace, owner_name)
    if owner_kind == "DaemonSet":
        return ("daemonset", namespace, owner_name)
    return None


def map_cronjob(obj: dict) -> dict:
    meta = obj.get("metadata", {})
    spec = obj.get("spec", {})
    status = obj.get("status", {})
    return {
        "namespace": meta.get("namespace", ""),
        "name": meta.get("name", ""),
        "schedule": spec.get("schedule"),
        "suspended": bool(spec.get("suspend")),
        "last_run_ts": _parse_time(status.get("lastScheduleTime")),
    }


def map_job_run(obj: dict) -> dict | None:
    """A Job owned by a CronJob → run record; None while still running."""
    meta = obj.get("metadata", {})
    status = obj.get("status", {})
    owners = meta.get("ownerReferences", [])
    owner = next((o for o in owners if o.get("kind") == "CronJob"), None)
    if owner is None:
        return None

    started = _parse_time(status.get("startTime"))
    finished = _parse_time(status.get("completionTime"))
    succeeded: bool | None = None
    failure_reason = None
    for condition in status.get("conditions", []):
        if condition.get("type") == "Complete" and condition.get("status") == "True":
            succeeded = True
        elif condition.get("type") == "Failed" and condition.get("status") == "True":
            succeeded = False
            failure_reason = condition.get("message") or condition.get("reason")
            finished = finished or _parse_time(condition.get("lastTransitionTime"))
    if succeeded is None:
        return None  # still running

    return {
        "cronjob_name": owner.get("name", ""),
        "namespace": meta.get("namespace", ""),
        "job_name": meta.get("name", ""),
        "started_ts": started,
        "finished_ts": finished,
        "succeeded": succeeded,
        "duration_s": (finished - started) if started and finished else None,
        "failure_reason": failure_reason,
    }
