package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"runtime"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/shirou/gopsutil/v4/host"

	"github.com/zurdi15/bifrost/agent/internal/collectors/dockermon"
	fscol "github.com/zurdi15/bifrost/agent/internal/collectors/fs"
	"github.com/zurdi15/bifrost/agent/internal/collectors/k8sdetect"
	smartcol "github.com/zurdi15/bifrost/agent/internal/collectors/smart"
	"github.com/zurdi15/bifrost/agent/internal/collectors/system"
	"github.com/zurdi15/bifrost/agent/internal/config"
	"github.com/zurdi15/bifrost/agent/internal/protocol"
	"github.com/zurdi15/bifrost/agent/internal/transport"
)

var version = "dev" // stamped by -ldflags at build time

func main() {
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))

	cfg, err := config.FromEnv()
	if err != nil {
		slog.Error("configuration error", "err", err)
		os.Exit(1)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	bootTS := int64(0)
	if bt, err := host.BootTimeWithContext(ctx); err == nil {
		bootTS = int64(bt)
	}

	caps := []string{"system"}
	docker := dockermon.New(dockermon.DefaultSocket)
	dockerAvailable := docker.Available(ctx)
	if dockerAvailable {
		caps = append(caps, "docker")
	}
	smart := smartcol.New()
	smartAvailable := smart.Available(ctx)
	if smartAvailable {
		caps = append(caps, "smart")
	}

	hello := protocol.NewHello(
		version, cfg.NodeName, runtime.GOOS, runtime.GOARCH, bootTS, caps,
	)

	client, err := transport.NewClient(cfg.HubURL, cfg.EnrollToken, system.Fingerprint(), hello)
	if err != nil {
		slog.Error("invalid hub url", "err", err)
		os.Exit(1)
	}

	// The hub can retune collection intervals live via config messages.
	var intervalSecs, fsIntervalSecs, smartIntervalSecs atomic.Int64
	intervalSecs.Store(int64(cfg.MetricsInterval / time.Second))
	fsIntervalSecs.Store(60)
	smartIntervalSecs.Store(1800)
	client.OnConfig = func(c protocol.AgentConfig) {
		if c.MetricsIntervalS > 0 {
			intervalSecs.Store(int64(c.MetricsIntervalS))
		}
		if c.FsIntervalS > 0 {
			fsIntervalSecs.Store(int64(c.FsIntervalS))
		}
		if c.SmartIntervalS > 0 {
			smartIntervalSecs.Store(int64(c.SmartIntervalS))
		}
	}

	go collectLoop(ctx, client, &intervalSecs)
	go fsLoop(ctx, client, &fsIntervalSecs)
	if dockerAvailable {
		go dockerLoop(ctx, client, docker)
		go statsLoop(ctx, client, docker)
	}
	if smartAvailable {
		go smartLoop(ctx, client, smart, &smartIntervalSecs)
	}
	go k8sDetectLoop(ctx, client)

	slog.Info("bifrost-agent starting",
		"version", version, "node", cfg.NodeName, "hub", cfg.HubURL,
		"docker", dockerAvailable, "smart", smartAvailable)
	client.Run(ctx)
	slog.Info("bifrost-agent stopped")
}

func collectLoop(ctx context.Context, client *transport.Client, intervalSecs *atomic.Int64) {
	collector := system.New()
	collector.Collect(ctx) // prime rate-based collectors (cpu%, net bps)

	for {
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Duration(intervalSecs.Load()) * time.Second):
		}
		samples := collector.Collect(ctx)
		if len(samples) == 0 {
			continue
		}
		send(client, protocol.NewMetrics(time.Now().Unix(), samples))
	}
}

func fsLoop(ctx context.Context, client *transport.Client, intervalSecs *atomic.Int64) {
	collector := fscol.New()
	if mounts := collector.Collect(ctx); len(mounts) > 0 {
		send(client, protocol.NewFs(time.Now().Unix(), mounts))
	}
	for {
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Duration(intervalSecs.Load()) * time.Second):
		}
		if mounts := collector.Collect(ctx); len(mounts) > 0 {
			send(client, protocol.NewFs(time.Now().Unix(), mounts))
		}
	}
}

// k8sDetectLoop reports clusters found on the host: once at start and on
// any change (rechecked every 10 minutes — k3s might get installed later).
func k8sDetectLoop(ctx context.Context, client *transport.Client) {
	hostRoot := os.Getenv("HOST_ROOT")
	lastHash := ""
	check := func() {
		detection := k8sdetect.Detect(hostRoot)
		if detection == nil || detection.Hash == lastHash {
			return
		}
		lastHash = detection.Hash
		slog.Info("kubernetes detected on host", "distro", detection.Distro)
		send(client, detection.Message(time.Now().Unix()))
	}
	check()
	for {
		select {
		case <-ctx.Done():
			return
		case <-time.After(10 * time.Minute):
		}
		check()
	}
}

func smartLoop(
	ctx context.Context, client *transport.Client,
	smart *smartcol.Collector, intervalSecs *atomic.Int64,
) {
	if disks := smart.Collect(ctx); len(disks) > 0 {
		send(client, protocol.NewSmart(time.Now().Unix(), disks))
	}
	for {
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Duration(intervalSecs.Load()) * time.Second):
		}
		if disks := smart.Collect(ctx); len(disks) > 0 {
			send(client, protocol.NewSmart(time.Now().Unix(), disks))
		}
	}
}

// statsLoop samples per-container cpu/mem every 15s. The first cycle only
// primes the cpu deltas; frames are dropped when nothing is running.
func statsLoop(ctx context.Context, client *transport.Client, docker *dockermon.Client) {
	collector := dockermon.NewStatsCollector(docker)
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			stats, err := collector.Collect(ctx)
			if err != nil || len(stats) == 0 {
				continue
			}
			send(client, protocol.NewContainerStats(time.Now().Unix(), stats))
		}
	}
}

// dockerLoop reconciles the container list on start, every minute and shortly
// after any lifecycle event; the events themselves stream to the hub live.
func dockerLoop(ctx context.Context, client *transport.Client, docker *dockermon.Client) {
	reconcile := func() {
		containers, err := docker.List(ctx)
		if err != nil {
			slog.Warn("docker list failed", "err", err)
			return
		}
		send(client, protocol.NewContainersFull(time.Now().Unix(), containers))
	}
	reconcile()

	events := make(chan dockermon.Event, 16)
	go func() {
		for ctx.Err() == nil {
			if err := docker.Events(ctx, events); err != nil && ctx.Err() == nil {
				slog.Warn("docker event stream lost, reconnecting", "err", err)
				select {
				case <-ctx.Done():
					return
				case <-time.After(5 * time.Second):
				}
			}
		}
	}()

	// Debounce timer: burst of events → one reconcile shortly after.
	var pendingReconcile *time.Timer
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			reconcile()
		case ev := <-events:
			send(client, protocol.NewContainerEvent(time.Now().Unix(), ev.Action,
				protocol.ContainerInfo{ContainerID: ev.ID, Name: ev.Name, Image: ev.Image}))
			if pendingReconcile != nil {
				pendingReconcile.Stop()
			}
			pendingReconcile = time.AfterFunc(1500*time.Millisecond, reconcile)
		}
	}
}

func send(client *transport.Client, msg protocol.Sequenced) {
	select {
	case client.Out <- msg:
	default:
		// Transport backlog (hub down, ring absorbing): drop this frame
		// rather than block collection forever.
	}
}
