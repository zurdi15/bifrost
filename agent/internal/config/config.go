package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// Config is read once from BIFROST_AGENT_* env vars. The agent is otherwise
// stateless; interval values are defaults the hub may override live.
type Config struct {
	HubURL          string
	EnrollToken     string
	NodeName        string
	MetricsInterval time.Duration
	// Download target for speedtests; latency/upload always use Cloudflare
	// anycast (nearest PoP). Pick a well-connected file server near you.
	SpeedtestURL string
	// Node UI declared at deploy time (a NAS dashboard, HAOS, …).
	UIPort int
	UIUrl  string
}

func FromEnv() (*Config, error) {
	hubURL := os.Getenv("BIFROST_AGENT_HUB_URL")
	if hubURL == "" {
		return nil, fmt.Errorf("BIFROST_AGENT_HUB_URL is required")
	}
	token := os.Getenv("BIFROST_AGENT_ENROLL_TOKEN")
	if token == "" {
		return nil, fmt.Errorf("BIFROST_AGENT_ENROLL_TOKEN is required")
	}

	speedtestURL := os.Getenv("BIFROST_AGENT_SPEEDTEST_URL")
	if speedtestURL == "" {
		speedtestURL = "https://fsn1-speed.hetzner.com/10GB.bin"
	}
	uiPort := 0
	if raw := os.Getenv("BIFROST_AGENT_UI_PORT"); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil {
			uiPort = parsed
		}
	}
	uiURL := os.Getenv("BIFROST_AGENT_UI_URL")
	name := os.Getenv("BIFROST_AGENT_NODE_NAME")
	if name == "" {
		name = hostHostname()
	}

	interval := 10 * time.Second
	if raw := os.Getenv("BIFROST_AGENT_METRICS_INTERVAL"); raw != "" {
		secs, err := strconv.Atoi(raw)
		if err != nil || secs < 1 {
			return nil, fmt.Errorf("invalid BIFROST_AGENT_METRICS_INTERVAL: %q", raw)
		}
		interval = time.Duration(secs) * time.Second
	}

	return &Config{
		HubURL:          hubURL,
		EnrollToken:     token,
		SpeedtestURL:    speedtestURL,
		UIPort:          uiPort,
		UIUrl:           uiURL,
		NodeName:        name,
		MetricsInterval: interval,
	}, nil
}

// hostHostname resolves the *host's* hostname. Inside Docker, os.Hostname()
// returns the container id. Note /proc/sys/kernel/hostname is useless here:
// procfs evaluates it in the READER's UTS namespace, so even a host /proc
// mount yields the container's hostname. /etc/hostname under the HOST_ROOT
// mount is a regular file and does carry the host's name.
func hostHostname() string {
	if hostRoot := os.Getenv("HOST_ROOT"); hostRoot != "" {
		if raw, err := os.ReadFile(filepath.Join(hostRoot, "etc/hostname")); err == nil {
			if name := strings.TrimSpace(string(raw)); name != "" {
				return name
			}
		}
	}
	// With uts: host (recommended in the example compose) this is the host's
	// hostname too — covers systems that don't persist /etc/hostname.
	name, _ := os.Hostname()
	return name
}
