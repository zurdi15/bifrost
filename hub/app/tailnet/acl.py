"""Tailscale ACL policy → who-can-reach-whom edges.

Best effort by design: the policy grammar keeps growing (grants, postures,
via routes) and a homelab map only needs the reachable-pairs truth. Every
selector the evaluator cannot ground to concrete devices lands in
`unresolved` instead of being silently dropped, so the UI can honestly say
"the map may be incomplete"."""

import ipaddress
import json
import re
from collections import defaultdict

from app.tailnet.model import Device

# Pseudo-node id for autogroup:internet traffic through exit nodes.
INTERNET = "internet"

_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
_PORT_SPEC = re.compile(r"^(\*|\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)$")

# Keep edge payloads bounded; a rule listing every port of a service mesh
# still renders as a readable chip row.
MAX_PORTS_PER_EDGE = 16


def parse_hujson(text: str) -> dict:
    """Tailscale policy files are HuJSON: JSON plus //, block comments and
    trailing commas. Strip those (string-aware) and hand off to json."""
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            i += 1
            continue
        if char == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if char == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(char)
        i += 1
    return json.loads(_TRAILING_COMMA.sub(r"\1", "".join(out)))


def _is_cidr(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return True


def parse_ports(spec: str, proto: str = "") -> list[str] | None:
    """"80,443" (+ proto "tcp") → ["80/tcp", "443/tcp"]; None when invalid."""
    if not _PORT_SPEC.match(spec):
        return None
    suffix = f"/{proto}" if proto else ""
    return [part + suffix for part in spec.split(",")]


def _sort_ports(ports: set[str]) -> list[str]:
    if "*" in ports:
        return ["*"]

    def key(port: str) -> tuple[int, int, str]:
        head = port.split("/")[0]
        if head == "*":
            return (0, 0, port)
        return (1, int(head.split("-")[0]), port)

    return sorted(ports, key=key)[:MAX_PORTS_PER_EDGE]


class PolicyGraph:
    """One policy evaluation pass over a concrete device list."""

    def __init__(self, policy: dict, devices: list[Device]) -> None:
        self.devices = devices
        self.groups: dict = policy.get("groups") or {}
        self.hosts: dict = policy.get("hosts") or {}
        self.unresolved: set[str] = set()
        self._members: dict[str, set[str]] = {}

    def group_members(self, name: str) -> set[str]:
        cached = self._members.get(name)
        if cached is not None:
            return cached
        self._members[name] = set()  # cycle guard for group-in-group loops
        members: set[str] = set()
        for entry in self.groups.get(name) or []:
            if isinstance(entry, str) and entry.startswith("group:"):
                members |= self.group_members(entry)
            elif isinstance(entry, str):
                members.add(entry)
        self._members[name] = members
        return members

    def _ip_match(self, spec: str, device: Device) -> bool:
        try:
            net = ipaddress.ip_network(spec, strict=False)
        except ValueError:
            return False
        for ip in device.ips:
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if addr.version == net.version and addr in net:
                return True
        return False

    def match(self, sel: str, device: Device) -> bool:
        """Does a src-style selector cover this device? Tagged devices lose
        their user identity, per Tailscale semantics."""
        if sel == "*":
            return True
        if sel.startswith("group:"):
            return not device.tags and device.user in self.group_members(sel)
        if sel.startswith("tag:"):
            return sel in device.tags
        if sel == "autogroup:member":
            return bool(device.user) and not device.tags and not device.external
        if sel == "autogroup:tagged":
            return bool(device.tags)
        if sel.startswith("autogroup:"):
            self.unresolved.add(sel)
            return False
        if "@" in sel:
            return not device.tags and device.user == sel
        if sel in self.hosts:
            return self._ip_match(str(self.hosts[sel]), device)
        if _is_cidr(sel):
            return self._ip_match(sel, device)
        self.unresolved.add(sel)
        return False

    def match_dst(self, target: str, src: Device, dst: Device) -> bool:
        if target == "autogroup:self":
            return bool(src.user) and not src.tags and not dst.tags and dst.user == src.user
        return self.match(target, dst)

    def reaches_internet(self, target: str) -> bool:
        """Targets that mean "the outside" (only meaningful via an exit node)."""
        if target in ("autogroup:internet", "*"):
            return True
        if _is_cidr(target):
            return ipaddress.ip_network(target, strict=False).prefixlen == 0
        return False


def build_edges(policy: dict, devices: list[Device]) -> tuple[list[dict], set[str], bool]:
    """(directed edges, unresolved selectors, internet pseudo-node used)."""
    graph = PolicyGraph(policy, devices)
    has_exit = any(d.exit_node for d in devices)
    edges: dict[tuple[str, str], set[str]] = defaultdict(set)

    def apply(srcs: list[Device], target: str, ports: list[str]) -> None:
        internet = has_exit and graph.reaches_internet(target)
        device_target = target != "autogroup:internet"
        for src in srcs:
            if internet:
                edges[(src.id, INTERNET)].update(ports)
            if not device_target:
                continue
            for dst in devices:
                if dst.id != src.id and graph.match_dst(target, src, dst):
                    edges[(src.id, dst.id)].update(ports)

    for rule in policy.get("acls") or []:
        if (rule.get("action") or "accept") != "accept":
            continue
        srcs = [d for d in devices if any(graph.match(s, d) for s in rule.get("src") or [])]
        if not srcs:
            continue
        proto = rule.get("proto") or ""
        for dst_spec in rule.get("dst") or []:
            target, _, port_spec = dst_spec.rpartition(":")
            ports = parse_ports(port_spec, proto) if target else None
            if not target or ports is None:
                graph.unresolved.add(dst_spec)
                continue
            apply(srcs, target, ports)

    for rule in policy.get("grants") or []:
        srcs = [d for d in devices if any(graph.match(s, d) for s in rule.get("src") or [])]
        ports: set[str] = set()
        for entry in rule.get("ip") or []:
            proto, _, spec = entry.rpartition(":")
            parsed = parse_ports(spec, proto)
            if parsed is None:
                graph.unresolved.add(entry)
            else:
                ports.update(parsed)
        if rule.get("app"):
            graph.unresolved.add("app grant")
        if not srcs or not ports:
            continue
        port_list = sorted(ports)
        for target in rule.get("dst") or []:
            apply(srcs, target, port_list)

    edge_list = [
        {"src": src, "dst": dst, "ports": _sort_ports(ports)}
        for (src, dst), ports in sorted(edges.items())
    ]
    internet_used = any(edge["dst"] == INTERNET for edge in edge_list)
    return edge_list, graph.unresolved, internet_used
