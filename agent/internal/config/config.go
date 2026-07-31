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
		NodeName:        name,
		MetricsInterval: interval,
	}, nil
}

// hostHostname resolves the *host's* hostname. Inside Docker, os.Hostname()
// returns the container id, so the host mounts the agent already has (HOST_PROC
// for gopsutil, HOST_ROOT for k8s detection) are tried first.
func hostHostname() string {
	candidates := []string{}
	if hostProc := os.Getenv("HOST_PROC"); hostProc != "" {
		candidates = append(candidates, filepath.Join(hostProc, "sys/kernel/hostname"))
	}
	if hostRoot := os.Getenv("HOST_ROOT"); hostRoot != "" {
		candidates = append(candidates, filepath.Join(hostRoot, "etc/hostname"))
	}
	for _, path := range candidates {
		if raw, err := os.ReadFile(path); err == nil {
			if name := strings.TrimSpace(string(raw)); name != "" {
				return name
			}
		}
	}
	name, _ := os.Hostname()
	return name
}
