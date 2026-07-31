import time
from dataclasses import dataclass, field

from fastapi import WebSocket


@dataclass
class AgentConn:
    node_id: int
    node_uuid: str
    ws: WebSocket
    connected_at: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)
    degraded: bool = False
    last_seq: int = 0
    # Freshest sample per metric name, for node-list summaries without a DB read.
    latest: dict[str, float] = field(default_factory=dict)
    latest_ts: int = 0


class AgentRegistry:
    """Live agent connections, keyed by node uuid. A reconnect replaces the
    previous entry; the old socket's cleanup must check `current_is(...)` before
    marking the node offline."""

    def __init__(self) -> None:
        self._conns: dict[str, AgentConn] = {}

    def add(self, conn: AgentConn) -> None:
        self._conns[conn.node_uuid] = conn

    def remove(self, conn: AgentConn) -> None:
        if self._conns.get(conn.node_uuid) is conn:
            del self._conns[conn.node_uuid]

    def get(self, node_uuid: str) -> AgentConn | None:
        return self._conns.get(node_uuid)

    def current_is(self, conn: AgentConn) -> bool:
        return self._conns.get(conn.node_uuid) is conn

    def all(self) -> list[AgentConn]:
        return list(self._conns.values())
