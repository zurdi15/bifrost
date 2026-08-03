"""Agent ↔ hub protocol v1.

This module is the canonical contract; `agent/internal/protocol/` mirrors it in Go.
Within a proto version changes must be additive only — both sides ignore unknown
fields. Bump PROTO_VERSION on breaking changes; the hub accepts N and N-1.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter

PROTO_VERSION = 1
MIN_PROTO_VERSION = 1


def _none_to_list(v: object) -> object:
    return [] if v is None else v


def _none_to_dict(v: object) -> object:
    return {} if v is None else v


# Go marshals nil slices/maps as JSON null; tolerate that everywhere.
StrList = Annotated[list[str], BeforeValidator(_none_to_list)]
StrMap = Annotated[dict[str, str], BeforeValidator(_none_to_dict)]


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ── agent → hub ──────────────────────────────────────────────────────────────


class Hello(_Msg):
    t: Literal["hello"]
    proto: int
    agent_version: str = ""
    hostname: str = ""
    os: str = ""
    arch: str = ""
    boot_ts: int = 0
    caps: StrList = []
    # Where the agent's seq counter currently stands. A freshly restarted
    # (stateless) agent declares 0 so the hub resets its dedup position
    # instead of discarding every new frame as a duplicate.
    start_seq: int = 0


class Sample(_Msg):
    name: str
    value: float


class Metrics(_Msg):
    t: Literal["metrics"]
    seq: int
    ts: int
    samples: list[Sample] = []


class FsMountInfo(_Msg):
    mountpoint: str
    device: str = ""
    fstype: str = ""
    total_bytes: int = 0
    used_bytes: int = 0
    stale: bool = False


class Fs(_Msg):
    t: Literal["fs"]
    seq: int
    ts: int
    mounts: list[FsMountInfo]


class ContainerInfo(_Msg):
    container_id: str
    name: str
    image: str = ""
    state: str = ""
    health: str = ""
    ports: StrList = []
    labels: StrMap = {}
    started_at: int = 0
    # "host" containers list their EXPOSE'd ports in `ports` (they listen on
    # the host directly); additive field, absent from older agents.
    network_mode: str = ""


class ContainersFull(_Msg):
    t: Literal["containers_full"]
    seq: int
    ts: int
    containers: list[ContainerInfo]


class ContainerEvent(_Msg):
    t: Literal["container_event"]
    seq: int
    ts: int
    action: str  # start | die | health_status | ...
    container: ContainerInfo


class ContainerStat(_Msg):
    container_id: str
    cpu_pct: float | None = None  # None on the first sample (needs a delta)
    mem_bytes: int | None = None
    mem_pct: float | None = None


class ContainerStats(_Msg):
    t: Literal["container_stats"]
    seq: int
    ts: int
    stats: list[ContainerStat] = []


class SmartDisk(_Msg):
    device: str
    model: str = ""
    serial: str = ""
    kind: str = ""  # hdd | ssd | nvme
    capacity_bytes: int = 0
    smart_status: str = "unknown"  # passed | failed | unknown
    temp_c: float | None = None
    power_on_hours: int | None = None
    realloc_sectors: int | None = None
    pending_sectors: int | None = None
    wear_pct: float | None = None
    raw_json: str = ""


class Smart(_Msg):
    t: Literal["smart"]
    seq: int
    ts: int
    disks: list[SmartDisk]


class K8sDetected(_Msg):
    t: Literal["k8s_detected"]
    seq: int
    ts: int
    distro: str = ""  # k3s | kubeadm | k0s
    version: str = ""
    api_endpoint: str = ""
    kubeconfig: str = ""  # content, when readable


class Heartbeat(_Msg):
    t: Literal["heartbeat"]
    seq: int
    ts: int


class Speedtest(BaseModel):
    """Hub→agent: run a speedtest and answer with the same id."""

    t: Literal["speedtest"] = "speedtest"
    id: int


class SpeedtestResult(_Msg):
    t: Literal["speedtest_result"]
    seq: int
    ts: int
    request_id: int = 0
    latency_ms: float | None = None
    download_mbps: float | None = None
    upload_mbps: float | None = None
    error: str = ""


AgentToHub = Annotated[
    Hello
    | Metrics
    | Fs
    | ContainersFull
    | ContainerEvent
    | ContainerStats
    | Smart
    | K8sDetected
    | SpeedtestResult
    | Heartbeat,
    Field(discriminator="t"),
]

_agent_adapter: TypeAdapter[AgentToHub] = TypeAdapter(AgentToHub)


def parse_agent_message(raw: str | bytes) -> AgentToHub:
    return _agent_adapter.validate_json(raw)


# ── hub → agent ──────────────────────────────────────────────────────────────


class AgentConfig(_Msg):
    metrics_interval_s: int = 10
    fs_interval_s: int = 60
    smart_interval_s: int = 1800
    heartbeat_interval_s: int = 15


class HelloAck(_Msg):
    t: Literal["hello_ack"] = "hello_ack"
    proto: int = PROTO_VERSION
    node_uuid: str
    agent_token: str | None = None  # only on enrollment
    config: AgentConfig = AgentConfig()
    resume_from_seq: int = 0


class Ack(_Msg):
    t: Literal["ack"] = "ack"
    upto_seq: int


class ConfigUpdate(_Msg):
    t: Literal["config"] = "config"
    config: AgentConfig


class Resync(_Msg):
    t: Literal["resync"] = "resync"


class ErrorMsg(_Msg):
    t: Literal["error"] = "error"
    code: str
    msg: str = ""


class Bye(_Msg):
    t: Literal["bye"] = "bye"
