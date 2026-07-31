import json

import pytest
from pydantic import ValidationError

from app.ingest import protocol as proto


def test_parse_hello():
    msg = proto.parse_agent_message(
        json.dumps({"t": "hello", "proto": 1, "hostname": "nas1", "caps": ["system"]})
    )
    assert isinstance(msg, proto.Hello)
    assert msg.hostname == "nas1"


def test_parse_metrics():
    msg = proto.parse_agent_message(
        json.dumps(
            {
                "t": "metrics",
                "seq": 7,
                "ts": 123,
                "samples": [{"name": "cpu.pct", "value": 42.5}],
            }
        )
    )
    assert isinstance(msg, proto.Metrics)
    assert msg.samples[0].value == 42.5


def test_unknown_fields_are_ignored():
    """Additive protocol evolution: newer agents may send fields we don't know."""
    msg = proto.parse_agent_message(
        json.dumps({"t": "heartbeat", "seq": 1, "ts": 5, "future_field": {"x": 1}})
    )
    assert isinstance(msg, proto.Heartbeat)


def test_unknown_message_type_rejected():
    with pytest.raises(ValidationError):
        proto.parse_agent_message(json.dumps({"t": "nonsense", "seq": 1}))


def test_hello_ack_roundtrip():
    ack = proto.HelloAck(node_uuid="abc", agent_token="tok", resume_from_seq=9)
    parsed = json.loads(ack.model_dump_json())
    assert parsed["t"] == "hello_ack"
    assert parsed["config"]["metrics_interval_s"] == 10
    assert parsed["resume_from_seq"] == 9
