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
	// Current seq counter position; 0 on a fresh process so the hub resets
	// its dedup position instead of dropping every new frame.
	StartSeq uint64 `json:"start_seq"`
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

// ContainerInfo mirrors the hub's ContainerInfo schema.
type ContainerInfo struct {
	ContainerID string            `json:"container_id"`
	Name        string            `json:"name"`
	Image       string            `json:"image"`
	State       string            `json:"state"`
	Health      string            `json:"health"`
	Ports       []string          `json:"ports"`
	Labels      map[string]string `json:"labels"`
	StartedAt   int64             `json:"started_at"`
}

type ContainersFull struct {
	T          string          `json:"t"`
	Seq        uint64          `json:"seq"`
	TS         int64           `json:"ts"`
	Containers []ContainerInfo `json:"containers"`
}

type ContainerEvent struct {
	T         string        `json:"t"`
	Seq       uint64        `json:"seq"`
	TS        int64         `json:"ts"`
	Action    string        `json:"action"`
	Container ContainerInfo `json:"container"`
}

// Sequenced is any agent→hub data frame the transport numbers and buffers.
type Sequenced interface{ SetSeq(seq uint64) }

func (m *Metrics) SetSeq(seq uint64)        { m.Seq = seq }
func (m *ContainersFull) SetSeq(seq uint64) { m.Seq = seq }
func (m *ContainerEvent) SetSeq(seq uint64) { m.Seq = seq }

func NewHello(agentVersion, hostname, osName, arch string, bootTS int64, caps []string) Hello {
	return Hello{
		T: "hello", Proto: Version, AgentVersion: agentVersion,
		Hostname: hostname, OS: osName, Arch: arch, BootTS: bootTS, Caps: caps,
	}
}

func NewMetrics(ts int64, samples []Sample) *Metrics {
	return &Metrics{T: "metrics", TS: ts, Samples: samples}
}

func NewContainersFull(ts int64, containers []ContainerInfo) *ContainersFull {
	return &ContainersFull{T: "containers_full", TS: ts, Containers: containers}
}

func NewContainerEvent(ts int64, action string, container ContainerInfo) *ContainerEvent {
	// Normalize nil slices/maps: they marshal as JSON null otherwise.
	if container.Ports == nil {
		container.Ports = []string{}
	}
	if container.Labels == nil {
		container.Labels = map[string]string{}
	}
	return &ContainerEvent{T: "container_event", TS: ts, Action: action, Container: container}
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
