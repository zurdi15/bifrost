// Package protocol mirrors hub/app/ingest/protocol.py (proto v1).
// Changes within a version are additive only; unknown JSON fields are ignored
// by both sides.
package protocol

import "encoding/json"

const Version = 1

// ── agent → hub ─────────────────────────────────────────────────────────────

type Hello struct {
	T            string   `json:"t"`
	Proto        int      `json:"proto"`
	AgentVersion string   `json:"agent_version"`
	Hostname     string   `json:"hostname"`
	OS           string   `json:"os"`
	Arch         string   `json:"arch"`
	BootTS       int64    `json:"boot_ts"`
	Caps         []string `json:"caps"`
}

type Sample struct {
	Name  string  `json:"name"`
	Value float64 `json:"value"`
}

type Metrics struct {
	T       string   `json:"t"`
	Seq     uint64   `json:"seq"`
	TS      int64    `json:"ts"`
	Samples []Sample `json:"samples"`
}

type Heartbeat struct {
	T   string `json:"t"`
	Seq uint64 `json:"seq"`
	TS  int64  `json:"ts"`
}

func NewHello(agentVersion, hostname, osName, arch string, bootTS int64, caps []string) Hello {
	return Hello{
		T: "hello", Proto: Version, AgentVersion: agentVersion,
		Hostname: hostname, OS: osName, Arch: arch, BootTS: bootTS, Caps: caps,
	}
}

func NewMetrics(seq uint64, ts int64, samples []Sample) Metrics {
	return Metrics{T: "metrics", Seq: seq, TS: ts, Samples: samples}
}

func NewHeartbeat(seq uint64, ts int64) Heartbeat {
	return Heartbeat{T: "heartbeat", Seq: seq, TS: ts}
}

// ── hub → agent ─────────────────────────────────────────────────────────────

type AgentConfig struct {
	MetricsIntervalS   int `json:"metrics_interval_s"`
	FsIntervalS        int `json:"fs_interval_s"`
	SmartIntervalS     int `json:"smart_interval_s"`
	HeartbeatIntervalS int `json:"heartbeat_interval_s"`
}

type HelloAck struct {
	T             string      `json:"t"`
	Proto         int         `json:"proto"`
	NodeUUID      string      `json:"node_uuid"`
	AgentToken    string      `json:"agent_token"`
	Config        AgentConfig `json:"config"`
	ResumeFromSeq uint64      `json:"resume_from_seq"`
}

type Ack struct {
	T       string `json:"t"`
	UptoSeq uint64 `json:"upto_seq"`
}

type ConfigUpdate struct {
	T      string      `json:"t"`
	Config AgentConfig `json:"config"`
}

type ErrorMsg struct {
	T    string `json:"t"`
	Code string `json:"code"`
	Msg  string `json:"msg"`
}

// Envelope peeks the discriminator so the reader can decode the right type.
type Envelope struct {
	T string `json:"t"`
}

func MessageType(raw []byte) (string, error) {
	var env Envelope
	if err := json.Unmarshal(raw, &env); err != nil {
		return "", err
	}
	return env.T, nil
}
