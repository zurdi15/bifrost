package dockermon

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/zurdi15/bifrost/agent/internal/protocol"
)

// statsSample is the subset of GET /containers/{id}/stats we consume.
type statsSample struct {
	CPUStats struct {
		CPUUsage struct {
			TotalUsage uint64 `json:"total_usage"`
		} `json:"cpu_usage"`
		SystemUsage uint64 `json:"system_cpu_usage"`
		OnlineCPUs  uint64 `json:"online_cpus"`
	} `json:"cpu_stats"`
	MemoryStats struct {
		Usage uint64            `json:"usage"`
		Limit uint64            `json:"limit"`
		Stats map[string]uint64 `json:"stats"`
	} `json:"memory_stats"`
}

type cpuPrev struct {
	total  uint64
	system uint64
}

// StatsCollector produces per-container cpu/mem usage. It uses one-shot
// stats reads (instant, unlike stream=false which blocks ~1s per container)
// and derives cpu% from the delta against the previous collection cycle —
// so the first cycle reports memory only.
type StatsCollector struct {
	client *Client
	prev   map[string]cpuPrev
}

func NewStatsCollector(client *Client) *StatsCollector {
	return &StatsCollector{client: client, prev: map[string]cpuPrev{}}
}

func (s *StatsCollector) statsOnce(ctx context.Context, id string) (*statsSample, error) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	url := s.client.base + "/containers/" + id + "/stats?stream=false&one-shot=true"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := s.client.httpc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("stats %s: HTTP %d", id[:min(12, len(id))], resp.StatusCode)
	}
	var sample statsSample
	if err := json.NewDecoder(resp.Body).Decode(&sample); err != nil {
		return nil, err
	}
	return &sample, nil
}

// Collect samples every running container. Individual failures skip the
// container; the previous-cycle state is pruned to running containers.
func (s *StatsCollector) Collect(ctx context.Context) ([]protocol.ContainerStat, error) {
	containers, err := s.client.List(ctx)
	if err != nil {
		return nil, err
	}
	stats := make([]protocol.ContainerStat, 0, len(containers))
	seen := map[string]bool{}
	for _, container := range containers {
		if container.State != "running" {
			continue
		}
		sample, err := s.statsOnce(ctx, container.ContainerID)
		if err != nil {
			continue
		}
		seen[container.ContainerID] = true
		stats = append(stats, s.toStat(container.ContainerID, sample))
	}
	for id := range s.prev {
		if !seen[id] {
			delete(s.prev, id)
		}
	}
	return stats, nil
}

func (s *StatsCollector) toStat(id string, sample *statsSample) protocol.ContainerStat {
	stat := protocol.ContainerStat{ContainerID: id}

	// Memory as `docker stats` reports it: usage minus page cache.
	mem := sample.MemoryStats.Usage
	for _, key := range []string{"inactive_file", "total_inactive_file"} {
		if cache, ok := sample.MemoryStats.Stats[key]; ok && cache < mem {
			mem -= cache
			break
		}
	}
	stat.MemBytes = &mem
	if limit := sample.MemoryStats.Limit; limit > 0 {
		pct := round2(float64(mem) * 100 / float64(limit))
		stat.MemPct = &pct
	}

	total := sample.CPUStats.CPUUsage.TotalUsage
	system := sample.CPUStats.SystemUsage
	if prev, ok := s.prev[id]; ok && system > prev.system && total >= prev.total {
		cpus := sample.CPUStats.OnlineCPUs
		if cpus == 0 {
			cpus = 1
		}
		pct := round2(
			float64(total-prev.total) / float64(system-prev.system) * float64(cpus) * 100,
		)
		stat.CPUPct = &pct
	}
	s.prev[id] = cpuPrev{total: total, system: system}
	return stat
}

func round2(v float64) float64 {
	return float64(int64(v*100+0.5)) / 100
}
