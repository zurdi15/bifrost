import hashlib
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import settings

ENROLL_TOKEN = "test-enroll-token"
FINGERPRINT = hashlib.sha256(b"machine-id-test").hexdigest()


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "enroll_token", ENROLL_TOKEN)
    monkeypatch.setattr(settings, "auto_approve", True)
    # Fast writer cadence so tests can wait milliseconds, not seconds.
    monkeypatch.setattr("app.metrics.store.FLUSH_INTERVAL_S", 0.05)

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def hello_frame(hostname: str = "testnode", proto: int = 1) -> str:
    return json.dumps(
        {
            "t": "hello",
            "proto": proto,
            "agent_version": "0.1.0-test",
            "hostname": hostname,
            "os": "linux",
            "arch": "amd64",
            "boot_ts": 1000,
            "caps": ["system"],
        }
    )


def metrics_frame(seq: int, ts: int, samples: dict[str, float]) -> str:
    return json.dumps(
        {
            "t": "metrics",
            "seq": seq,
            "ts": ts,
            "samples": [{"name": k, "value": v} for k, v in samples.items()],
        }
    )


def agent_headers(token: str = ENROLL_TOKEN, fingerprint: str = FINGERPRINT) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Bifrost-Fingerprint": fingerprint,
    }
