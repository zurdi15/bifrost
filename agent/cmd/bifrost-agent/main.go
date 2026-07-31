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

	hello := protocol.NewHello(
		version, cfg.NodeName, runtime.GOOS, runtime.GOARCH, bootTS, []string{"system"},
	)

	client, err := transport.NewClient(cfg.HubURL, cfg.EnrollToken, system.Fingerprint(), hello)
	if err != nil {
		slog.Error("invalid hub url", "err", err)
		os.Exit(1)
	}

	// The hub can retune the collection interval live via config messages.
	var intervalSecs atomic.Int64
	intervalSecs.Store(int64(cfg.MetricsInterval / time.Second))
	client.OnConfig = func(c protocol.AgentConfig) {
		if c.MetricsIntervalS > 0 {
			intervalSecs.Store(int64(c.MetricsIntervalS))
		}
	}

	go collectLoop(ctx, client, &intervalSecs)

	slog.Info("bifrost-agent starting", "version", version, "node", cfg.NodeName, "hub", cfg.HubURL)
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
		select {
		case client.Frames <- samples:
		default:
			// Transport backlog (hub down, ring absorbing): drop this round
			// rather than block collection forever.
		}
	}
}
