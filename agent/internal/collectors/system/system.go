// Package system collects node metrics via gopsutil, honoring HOST_PROC /
// HOST_SYS / HOST_ROOT so it reads the host, not the container.
package system

import (
	"context"
	"log/slog"
	"regexp"
	"strings"
	"time"

	"github.com/shirou/gopsutil/v4/cpu"
	"github.com/shirou/gopsutil/v4/load"
	"github.com/shirou/gopsutil/v4/mem"
	gopsnet "github.com/shirou/gopsutil/v4/net"
	"github.com/shirou/gopsutil/v4/sensors"

	"github.com/zurdi15/bifrost/agent/internal/protocol"
)

// CPU temperature sensor keys, in preference order. Covers Intel (coretemp),
// AMD (k10temp) and Raspberry Pi (cpu_thermal) hardware.
var cpuTempKeys = []string{"coretemp_package_id_0", "k10temp_tctl", "k10temp", "cpu_thermal", "coretemp_core_0", "soc_thermal"}

var nameSanitizer = regexp.MustCompile(`[^a-z0-9_.-]+`)

func sanitize(name string) string {
	return nameSanitizer.ReplaceAllString(strings.ToLower(name), "_")
}

type netState struct {
	rx, tx uint64
	at     time.Time
}

type Collector struct {
	prevNet map[string]netState
}

func New() *Collector {
	return &Collector{prevNet: map[string]netState{}}
}

// Collect gathers one round of samples. Individual collector failures are
// logged and skipped — a NAS without readable sensors still reports CPU/mem.
func (c *Collector) Collect(ctx context.Context) []protocol.Sample {
	now := time.Now()
	samples := make([]protocol.Sample, 0, 32)
	add := func(name string, value float64) {
		samples = append(samples, protocol.Sample{Name: name, Value: value})
	}

	if pcts, err := cpu.PercentWithContext(ctx, 0, false); err == nil && len(pcts) > 0 {
		add("cpu.pct", round2(pcts[0]))
	} else if err != nil {
		slog.Debug("cpu collector failed", "err", err)
	}

	if avg, err := load.AvgWithContext(ctx); err == nil {
		add("cpu.load1", round2(avg.Load1))
		add("cpu.load5", round2(avg.Load5))
		add("cpu.load15", round2(avg.Load15))
	}

	if vm, err := mem.VirtualMemoryWithContext(ctx); err == nil {
		add("mem.total", float64(vm.Total))
		add("mem.used", float64(vm.Used))
		add("mem.pct", round2(vm.UsedPercent))
	}
	if sw, err := mem.SwapMemoryWithContext(ctx); err == nil && sw.Total > 0 {
		add("swap.total", float64(sw.Total))
		add("swap.used", float64(sw.Used))
	}

	c.collectNet(ctx, now, add)
	c.collectTemps(ctx, add)

	return samples
}

func (c *Collector) collectNet(ctx context.Context, now time.Time, add func(string, float64)) {
	counters, err := gopsnet.IOCountersWithContext(ctx, true)
	if err != nil {
		return
	}
	for _, nic := range counters {
		if nic.Name == "lo" || strings.HasPrefix(nic.Name, "veth") || strings.HasPrefix(nic.Name, "br-") {
			continue
		}
		prev, seen := c.prevNet[nic.Name]
		c.prevNet[nic.Name] = netState{rx: nic.BytesRecv, tx: nic.BytesSent, at: now}
		if !seen {
			continue // first round: no rate yet
		}
		dt := now.Sub(prev.at).Seconds()
		if dt <= 0 || nic.BytesRecv < prev.rx || nic.BytesSent < prev.tx {
			continue // counter reset (interface bounce)
		}
		name := sanitize(nic.Name)
		add("net."+name+".rx_bps", round2(float64(nic.BytesRecv-prev.rx)/dt))
		add("net."+name+".tx_bps", round2(float64(nic.BytesSent-prev.tx)/dt))
	}
}

func (c *Collector) collectTemps(ctx context.Context, add func(string, float64)) {
	temps, err := sensors.TemperaturesWithContext(ctx)
	if err != nil || len(temps) == 0 {
		return
	}
	byKey := map[string]float64{}
	for _, t := range temps {
		if t.Temperature <= 0 {
			continue
		}
		key := sanitize(t.SensorKey)
		if _, dup := byKey[key]; !dup {
			byKey[key] = t.Temperature
			add("temp."+key, round2(t.Temperature))
		}
	}
	for _, key := range cpuTempKeys {
		if v, ok := byKey[key]; ok {
			add("temp.cpu", round2(v))
			return
		}
	}
	// Fallback: any sensor beats no CPU temperature on exotic hardware.
	for _, key := range cpuTempKeys {
		for k, v := range byKey {
			if strings.Contains(k, key) {
				add("temp.cpu", round2(v))
				return
			}
		}
	}
}

func round2(v float64) float64 {
	return float64(int64(v*100+0.5)) / 100
}
