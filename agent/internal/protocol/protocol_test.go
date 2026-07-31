package protocol

import (
	"encoding/json"
	"testing"
)

func TestMetricsRoundtrip(t *testing.T) {
	msg := NewMetrics(7, 1234, []Sample{{Name: "cpu.pct", Value: 42.5}})
	raw, err := json.Marshal(msg)
	if err != nil {
		t.Fatal(err)
	}
	msgType, err := MessageType(raw)
	if err != nil || msgType != "metrics" {
		t.Fatalf("MessageType = %q, %v", msgType, err)
	}
	var back Metrics
	if err := json.Unmarshal(raw, &back); err != nil {
		t.Fatal(err)
	}
	if back.Seq != 7 || back.Samples[0].Value != 42.5 {
		t.Fatalf("roundtrip mismatch: %+v", back)
	}
}

func TestHelloAckUnknownFieldsIgnored(t *testing.T) {
	raw := []byte(`{"t":"hello_ack","proto":1,"node_uuid":"abc","agent_token":"tok",
		"config":{"metrics_interval_s":5,"future_knob":true},"resume_from_seq":3,"new_field":1}`)
	var ack HelloAck
	if err := json.Unmarshal(raw, &ack); err != nil {
		t.Fatal(err)
	}
	if ack.NodeUUID != "abc" || ack.Config.MetricsIntervalS != 5 || ack.ResumeFromSeq != 3 {
		t.Fatalf("parse mismatch: %+v", ack)
	}
}

func TestHelloShape(t *testing.T) {
	raw, _ := json.Marshal(NewHello("0.1.0", "nas1", "linux", "arm64", 99, []string{"system"}))
	var m map[string]any
	_ = json.Unmarshal(raw, &m)
	for _, key := range []string{"t", "proto", "agent_version", "hostname", "os", "arch", "boot_ts", "caps"} {
		if _, ok := m[key]; !ok {
			t.Fatalf("hello missing %q: %s", key, raw)
		}
	}
}
