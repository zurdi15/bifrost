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
	// Declarative node UI; zero values mean "not declared".
	UIPort int    `json:"ui_port,omitempty"`
	UIUrl  string `json:"ui_url,omitempty"`
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

// FsMountInfo mirrors the hub's FsMountInfo schema.
type FsMountInfo struct {
	Mountpoint string `json:"mountpoint"`
	Device     string `json:"device"`
	Fstype     string `json:"fstype"`
	TotalBytes int64  `json:"total_bytes"`
	UsedBytes  int64  `json:"used_bytes"`
	Stale      bool   `json:"stale"`
}

type Fs struct {
	T      string        `json:"t"`
	Seq    uint64        `json:"seq"`
	TS     int64         `json:"ts"`
	Mounts []FsMountInfo `json:"mounts"`
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
	// "host" containers list their EXPOSE'd ports in Ports — they listen on
	// the host directly. Additive field; the hub defaults it to empty.
	NetworkMode string `json:"network_mode,omitempty"`
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

// ContainerStat mirrors the hub's ContainerStat schema. CPUPct is nil on the
// first sample: usage percentages need a delta between two reads.
type ContainerStat struct {
	ContainerID string   `json:"container_id"`
	CPUPct      *float64 `json:"cpu_pct"`
	MemBytes    *uint64  `json:"mem_bytes"`
	MemPct      *float64 `json:"mem_pct"`
}

type ContainerStats struct {
	T     string          `json:"t"`
	Seq   uint64          `json:"seq"`
	TS    int64           `json:"ts"`
	Stats []ContainerStat `json:"stats"`
}

// SmartDisk mirrors the hub's SmartDisk schema.
type SmartDisk struct {
	Device         string   `json:"device"`
	Model          string   `json:"model"`
	Serial         string   `json:"serial"`
	Kind           string   `json:"kind"`
	CapacityBytes  int64    `json:"capacity_bytes"`
	SmartStatus    string   `json:"smart_status"`
	TempC          *float64 `json:"temp_c"`
	PowerOnHours   *int64   `json:"power_on_hours"`
	ReallocSectors *int64   `json:"realloc_sectors"`
	PendingSectors *int64   `json:"pending_sectors"`
	WearPct        *float64 `json:"wear_pct"`
	RawJSON        string   `json:"raw_json"`
}

type Smart struct {
	T     string      `json:"t"`
	Seq   uint64      `json:"seq"`
	TS    int64       `json:"ts"`
	Disks []SmartDisk `json:"disks"`
}

type K8sDetected struct {
	T           string `json:"t"`
	Seq         uint64 `json:"seq"`
	TS          int64  `json:"ts"`
	Distro      string `json:"distro"`
	Version     string `json:"version"`
	APIEndpoint string `json:"api_endpoint"`
	Kubeconfig  string `json:"kubeconfig"`
}

// SpeedtestResult answers a hub-triggered speedtest request.
type SpeedtestResult struct {
	T            string  `json:"t"`
	Seq          uint64  `json:"seq"`
	TS           int64   `json:"ts"`
	RequestID    int64   `json:"request_id"`
	LatencyMs    float64 `json:"latency_ms"`
	DownloadMbps float64 `json:"download_mbps"`
	UploadMbps   float64 `json:"upload_mbps"`
	Error        string  `json:"error,omitempty"`
}

// Sequenced is any agent→hub data frame the transport numbers and buffers.
type Sequenced interface{ SetSeq(seq uint64) }

func (m *Metrics) SetSeq(seq uint64)         { m.Seq = seq }
func (m *Fs) SetSeq(seq uint64)              { m.Seq = seq }
func (m *ContainersFull) SetSeq(seq uint64)  { m.Seq = seq }
func (m *ContainerEvent) SetSeq(seq uint64)  { m.Seq = seq }
func (m *ContainerStats) SetSeq(seq uint64)  { m.Seq = seq }
func (m *Smart) SetSeq(seq uint64)           { m.Seq = seq }
func (m *K8sDetected) SetSeq(seq uint64)     { m.Seq = seq }
func (m *SpeedtestResult) SetSeq(seq uint64) { m.Seq = seq }

func NewHello(agentVersion, hostname, osName, arch string, bootTS int64, caps []string) Hello {
	return Hello{
		T: "hello", Proto: Version, AgentVersion: agentVersion,
		Hostname: hostname, OS: osName, Arch: arch, BootTS: bootTS, Caps: caps,
	}
}

func NewMetrics(ts int64, samples []Sample) *Metrics {
	return &Metrics{T: "metrics", TS: ts, Samples: samples}
}

func NewFs(ts int64, mounts []FsMountInfo) *Fs {
	if mounts == nil {
		mounts = []FsMountInfo{}
	}
	return &Fs{T: "fs", TS: ts, Mounts: mounts}
}

func NewContainersFull(ts int64, containers []ContainerInfo) *ContainersFull {
	return &ContainersFull{T: "containers_full", TS: ts, Containers: containers}
}

func NewContainerStats(ts int64, stats []ContainerStat) *ContainerStats {
	return &ContainerStats{T: "container_stats", TS: ts, Stats: stats}
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

func NewSmart(ts int64, disks []SmartDisk) *Smart {
	if disks == nil {
		disks = []SmartDisk{}
	}
	return &Smart{T: "smart", TS: ts, Disks: disks}
}

func NewK8sDetected(ts int64, distro, apiEndpoint, kubeconfig string) *K8sDetected {
	return &K8sDetected{
		T: "k8s_detected", TS: ts, Distro: distro,
		APIEndpoint: apiEndpoint, Kubeconfig: kubeconfig,
	}
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
