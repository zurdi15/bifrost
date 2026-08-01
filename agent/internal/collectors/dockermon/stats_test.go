package dockermon

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func statsServer(t *testing.T, cycle *int) *Client {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/containers/json", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `[
			{"Id":"aaa111","Names":["/romm"],"State":"running","Status":"Up 2 hours"},
			{"Id":"bbb222","Names":["/stopped"],"State":"exited","Status":"Exited"}
		]`)
	})
	mux.HandleFunc("/containers/aaa111/stats", func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.RawQuery, "one-shot=true") {
			t.Errorf("stats must use one-shot reads, got %q", r.URL.RawQuery)
		}
		// Cycle 1: total=100e6 of system=1000e6. Cycle 2: +50e6 of +500e6
		// with 4 cpus → 10% * 4 = 40%.
		total, system := uint64(100e6), uint64(1000e6)
		if *cycle > 0 {
			total, system = uint64(150e6), uint64(1500e6)
		}
		payload := map[string]any{
			"cpu_stats": map[string]any{
				"cpu_usage":        map[string]any{"total_usage": total},
				"system_cpu_usage": system,
				"online_cpus":      4,
			},
			"memory_stats": map[string]any{
				"usage": 300 * 1024 * 1024,
				"limit": 1024 * 1024 * 1024,
				"stats": map[string]uint64{"inactive_file": 100 * 1024 * 1024},
			},
		}
		_ = json.NewEncoder(w).Encode(payload)
	})
	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)
	return NewForURL(server.URL)
}

func TestStatsCollectorDeltas(t *testing.T) {
	cycle := 0
	collector := NewStatsCollector(statsServer(t, &cycle))

	first, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	// Only the running container is sampled; first cycle has no cpu yet.
	if len(first) != 1 || first[0].ContainerID != "aaa111" {
		t.Fatalf("want one running container, got %+v", first)
	}
	if first[0].CPUPct != nil {
		t.Fatalf("first cycle must not report cpu, got %v", *first[0].CPUPct)
	}
	// Memory = usage - inactive_file (docker stats semantics).
	if *first[0].MemBytes != 200*1024*1024 {
		t.Fatalf("want mem 200MiB, got %d", *first[0].MemBytes)
	}
	if pct := *first[0].MemPct; pct < 19.5 || pct > 19.6 {
		t.Fatalf("want mem pct ≈19.53, got %v", pct)
	}

	cycle = 1
	second, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if second[0].CPUPct == nil || *second[0].CPUPct != 40.0 {
		t.Fatalf("want cpu 40%% from delta, got %+v", second[0].CPUPct)
	}
}
