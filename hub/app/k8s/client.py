"""Thin async Kubernetes API client over httpx.

Auth comes either from a token (+CA) or from a kubeconfig (token or client
certificate). Client certs need real files for TLS, so they materialize under
data_dir/k8s/<cluster_id>/.
"""

import base64
import ssl
import tempfile
from pathlib import Path

import httpx
import yaml


class K8sAuthError(Exception):
    pass


def build_ssl_context(
    ca_pem: str | None,
    client_cert_pem: str | None = None,
    client_key_pem: str | None = None,
    cert_dir: Path | None = None,
) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if ca_pem:
        # The CA is the cluster's own private CA (pinned from its kubeconfig),
        # so chain verification alone already identifies the cluster. Hostname
        # checking must be off: discovered clusters are reached through a
        # rewritten address (the one the agent connected from — e.g. a
        # Tailscale IP) that is never in the apiserver cert's SANs.
        context.check_hostname = False
        context.load_verify_locations(cadata=ca_pem)
    if client_cert_pem and client_key_pem:
        cert_dir = cert_dir or Path(tempfile.mkdtemp(prefix="bifrost-k8s-"))
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_file = cert_dir / "client.pem"
        key_file = cert_dir / "client-key.pem"
        cert_file.write_text(client_cert_pem)
        key_file.write_text(client_key_pem)
        key_file.chmod(0o600)
        context.load_cert_chain(str(cert_file), str(key_file))
    return context


def parse_kubeconfig(content: str) -> dict:
    """Extract server/CA/credentials from the first context of a kubeconfig."""
    try:
        cfg = yaml.safe_load(content) or {}
        cluster = cfg["clusters"][0]["cluster"]
        user = cfg["users"][0]["user"]
    except (KeyError, IndexError, TypeError, yaml.YAMLError) as exc:
        raise K8sAuthError(f"unparseable kubeconfig: {exc}") from exc

    def b64(key: str, source: dict) -> str | None:
        value = source.get(key)
        return base64.b64decode(value).decode() if value else None

    return {
        "server": cluster.get("server", ""),
        "ca_pem": b64("certificate-authority-data", cluster),
        "token": user.get("token"),
        "client_cert_pem": b64("client-certificate-data", user),
        "client_key_pem": b64("client-key-data", user),
    }


def rewrite_localhost(server: str, node_address: str) -> str:
    """k3s writes server: https://127.0.0.1:6443 — rewrite to the address the
    agent actually connected from so the hub can reach the API."""
    for local in ("127.0.0.1", "localhost", "0.0.0.0"):
        if f"//{local}:" in server or server.endswith(f"//{local}"):
            return server.replace(f"//{local}", f"//{node_address}")
    return server


class K8sClient:
    def __init__(
        self,
        api_url: str,
        *,
        token: str | None = None,
        ca_pem: str | None = None,
        client_cert_pem: str | None = None,
        client_key_pem: str | None = None,
        insecure: bool = False,
        cert_dir: Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        verify: ssl.SSLContext | bool
        if insecure:
            verify = False
        elif ca_pem or client_cert_pem:
            verify = build_ssl_context(ca_pem, client_cert_pem, client_key_pem, cert_dir)
        else:
            verify = True

        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            headers=headers,
            verify=verify if transport is None else True,
            timeout=httpx.Timeout(10.0, read=30.0),
            transport=transport,
        )

    @classmethod
    def from_cluster(cls, cluster, cert_dir: Path | None = None) -> "K8sClient":  # noqa: ANN001
        """Build from a K8sCluster row (manual token/URL or stored kubeconfig)."""
        if cluster.kubeconfig_content:
            parsed = parse_kubeconfig(cluster.kubeconfig_content)
            return cls(
                cluster.api_url or parsed["server"],
                token=parsed["token"],
                ca_pem=parsed["ca_pem"],
                client_cert_pem=parsed["client_cert_pem"],
                client_key_pem=parsed["client_key_pem"],
                insecure=cluster.insecure_skip_verify,
                cert_dir=cert_dir,
            )
        if cluster.kubeconfig_path:
            content = Path(cluster.kubeconfig_path).read_text()
            parsed = parse_kubeconfig(content)
            return cls(
                cluster.api_url or parsed["server"],
                token=parsed["token"],
                ca_pem=parsed["ca_pem"],
                client_cert_pem=parsed["client_cert_pem"],
                client_key_pem=parsed["client_key_pem"],
                insecure=cluster.insecure_skip_verify,
                cert_dir=cert_dir,
            )
        if not cluster.api_url:
            raise K8sAuthError("cluster has neither kubeconfig nor api_url")
        return cls(
            cluster.api_url,
            token=cluster.token,
            ca_pem=cluster.ca_pem,
            insecure=cluster.insecure_skip_verify,
        )

    async def get(self, path: str) -> dict:
        response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    async def list_items(self, path: str) -> list[dict]:
        return (await self.get(path)).get("items", [])

    async def version(self) -> str:
        data = await self.get("/version")
        return data.get("gitVersion", "")

    async def close(self) -> None:
        await self._client.aclose()
