import time
import uuid as uuidlib

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_ts() -> int:
    return int(time.time())


def new_uuid() -> str:
    return str(uuidlib.uuid4())


class Base(DeclarativeBase):
    pass


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(unique=True, default=new_uuid)
    fingerprint: Mapped[str | None] = mapped_column(unique=True)  # NULL for kind='endpoint'
    name: Mapped[str]
    # Last hostname the agent reported. `name` follows it until the user
    # renames the node explicitly (name != hostname ⇒ custom, never touched).
    hostname: Mapped[str | None]
    kind: Mapped[str] = mapped_column(default="agent")  # 'agent' | 'endpoint'
    status: Mapped[str] = mapped_column(default="pending")
    os: Mapped[str | None]
    arch: Mapped[str | None]
    agent_version: Mapped[str | None]
    boot_ts: Mapped[int | None]
    labels_json: Mapped[str] = mapped_column(default="{}")
    token_hash: Mapped[str | None]  # sha256 of the per-agent token
    last_seq: Mapped[int] = mapped_column(default=0)
    approved_at: Mapped[int | None]
    last_seen: Mapped[int | None]
    created_at: Mapped[int] = mapped_column(default=now_ts)


class Container(Base):
    __tablename__ = "containers"
    __table_args__ = (UniqueConstraint("node_id", "container_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    container_id: Mapped[str]
    name: Mapped[str]
    image: Mapped[str | None]
    state: Mapped[str | None]
    health: Mapped[str | None]
    ports_json: Mapped[str | None]
    labels_json: Mapped[str | None]
    bifrost_meta_json: Mapped[str | None]  # {icon,url,group,hide} from bifrost.* labels
    started_at: Mapped[int | None]
    updated_at: Mapped[int] = mapped_column(default=now_ts)


class ServiceOverride(Base):
    """User-set display metadata for a container, keyed by name (not id) so it
    survives container recreation. Fields override bifrost.* label meta; NULL
    means inherit."""

    __tablename__ = "service_overrides"
    __table_args__ = (UniqueConstraint("node_id", "container_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    container_name: Mapped[str]
    name: Mapped[str | None]
    icon: Mapped[str | None]
    url: Mapped[str | None]
    group_name: Mapped[str | None]
    hide: Mapped[bool | None]


class FsMount(Base):
    __tablename__ = "fs_mounts"
    __table_args__ = (UniqueConstraint("node_id", "mountpoint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    mountpoint: Mapped[str]
    device: Mapped[str | None]
    fstype: Mapped[str | None]
    total_bytes: Mapped[int | None]
    used_bytes: Mapped[int | None]
    stale: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[int] = mapped_column(default=now_ts)


class Disk(Base):
    __tablename__ = "disks"
    __table_args__ = (UniqueConstraint("node_id", "serial"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    device: Mapped[str]
    model: Mapped[str | None]
    serial: Mapped[str]
    kind: Mapped[str | None]  # hdd | ssd | nvme
    capacity_bytes: Mapped[int | None]
    smart_status: Mapped[str | None]  # passed | failed | unknown
    temp_c: Mapped[float | None]
    power_on_hours: Mapped[int | None]
    realloc_sectors: Mapped[int | None]
    pending_sectors: Mapped[int | None]
    wear_pct: Mapped[float | None]
    smart_json: Mapped[str | None]
    updated_at: Mapped[int] = mapped_column(default=now_ts)


class K8sCluster(Base):
    __tablename__ = "k8s_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    source: Mapped[str] = mapped_column(default="manual")  # 'manual' | 'discovered'
    discovered_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL")
    )
    auth_mode: Mapped[str] = mapped_column(default="token")  # 'kubeconfig' | 'token'
    kubeconfig_path: Mapped[str | None]
    kubeconfig_content: Mapped[str | None]  # discovered clusters (agent-shipped)
    api_url: Mapped[str | None]
    token: Mapped[str | None]
    ca_pem: Mapped[str | None]
    insecure_skip_verify: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str | None]
    last_sync: Mapped[int | None]


class K8sWorkload(Base):
    __tablename__ = "k8s_workloads"
    __table_args__ = (UniqueConstraint("cluster_id", "kind", "namespace", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("k8s_clusters.id", ondelete="CASCADE"))
    kind: Mapped[str]  # deployment | daemonset | statefulset
    namespace: Mapped[str]
    name: Mapped[str]
    replicas_desired: Mapped[int | None]
    replicas_ready: Mapped[int | None]
    images_json: Mapped[str | None]
    labels_json: Mapped[str | None]
    updated_at: Mapped[int] = mapped_column(default=now_ts)


class K8sPod(Base):
    __tablename__ = "k8s_pods"
    __table_args__ = (UniqueConstraint("cluster_id", "namespace", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("k8s_clusters.id", ondelete="CASCADE"))
    namespace: Mapped[str]
    name: Mapped[str]
    phase: Mapped[str | None]
    ready: Mapped[bool | None]
    restarts: Mapped[int | None]
    node_name: Mapped[str | None]
    owner_kind: Mapped[str | None]
    owner_name: Mapped[str | None]
    updated_at: Mapped[int] = mapped_column(default=now_ts)


class K8sService(Base):
    __tablename__ = "k8s_services"
    __table_args__ = (UniqueConstraint("cluster_id", "namespace", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("k8s_clusters.id", ondelete="CASCADE"))
    namespace: Mapped[str]
    name: Mapped[str]
    type: Mapped[str | None]
    cluster_ip: Mapped[str | None]
    ports_json: Mapped[str | None]
    updated_at: Mapped[int] = mapped_column(default=now_ts)


class K8sIngress(Base):
    __tablename__ = "k8s_ingresses"
    __table_args__ = (UniqueConstraint("cluster_id", "namespace", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("k8s_clusters.id", ondelete="CASCADE"))
    namespace: Mapped[str]
    name: Mapped[str]
    hosts_json: Mapped[str | None]
    tls: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[int] = mapped_column(default=now_ts)


class K8sCronJob(Base):
    __tablename__ = "k8s_cronjobs"
    __table_args__ = (UniqueConstraint("cluster_id", "namespace", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("k8s_clusters.id", ondelete="CASCADE"))
    namespace: Mapped[str]
    name: Mapped[str]
    schedule: Mapped[str | None]
    suspended: Mapped[bool] = mapped_column(default=False)
    last_run_ts: Mapped[int | None]
    last_result: Mapped[str | None]
    last_duration_s: Mapped[int | None]
    updated_at: Mapped[int] = mapped_column(default=now_ts)


class K8sJobRun(Base):
    __tablename__ = "k8s_job_runs"
    __table_args__ = (UniqueConstraint("cronjob_id", "job_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cronjob_id: Mapped[int] = mapped_column(ForeignKey("k8s_cronjobs.id", ondelete="CASCADE"))
    job_name: Mapped[str]
    started_ts: Mapped[int | None]
    finished_ts: Mapped[int | None]
    succeeded: Mapped[bool | None]
    duration_s: Mapped[int | None]
    failure_reason: Mapped[str | None]


class EndpointCheck(Base):
    __tablename__ = "endpoint_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    check_kind: Mapped[str]  # 'ping' | 'http' | 'tcp'
    target: Mapped[str]
    interval_s: Mapped[int] = mapped_column(default=30)
    timeout_s: Mapped[int] = mapped_column(default=5)
    expect_status: Mapped[int | None]
    last_ok: Mapped[bool | None]
    last_latency_ms: Mapped[float | None]
    last_checked: Mapped[int | None]


class Widget(Base):
    __tablename__ = "widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str]
    title: Mapped[str | None]
    config_json: Mapped[str] = mapped_column(default="{}")
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[int] = mapped_column(default=now_ts)


class Dashboard(Base):
    __tablename__ = "dashboards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    layout_json: Mapped[str] = mapped_column(default="{}")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value_json: Mapped[str]


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    # Event topic to match ('node.status', 'k8s.cronjob.run', … or '*').
    kind: Mapped[str] = mapped_column(default="*")
    min_severity: Mapped[str] = mapped_column(default="warning")  # info | warning
    notifier: Mapped[str]  # 'ntfy' | 'webhook'
    target: Mapped[str]  # ntfy topic URL / webhook URL
    cooldown_s: Mapped[int] = mapped_column(default=300)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[int] = mapped_column(default=now_ts)


class DbEvent(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_ts", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[int]
    kind: Mapped[str]
    severity: Mapped[str] = mapped_column(default="info")
    node_id: Mapped[int | None]
    subject: Mapped[str | None]
    payload_json: Mapped[str | None]
