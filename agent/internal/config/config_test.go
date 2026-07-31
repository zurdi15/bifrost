package config

import (
	"os"
	"path/filepath"
	"testing"
)

// Regression: inside Docker, os.Hostname() is the container id. The host's
// hostname must come from the host mounts when they are available.
func TestHostHostnamePrefersHostMounts(t *testing.T) {
	dir := t.TempDir()

	proc := filepath.Join(dir, "proc")
	if err := os.MkdirAll(filepath.Join(proc, "sys/kernel"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(proc, "sys/kernel/hostname"), []byte("gateway\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	root := filepath.Join(dir, "rootfs")
	if err := os.MkdirAll(filepath.Join(root, "etc"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "etc/hostname"), []byte("gateway-etc\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("HOST_PROC", proc)
	t.Setenv("HOST_ROOT", root)
	if got := hostHostname(); got != "gateway" {
		t.Fatalf("want hostname from HOST_PROC, got %q", got)
	}

	// Without /proc, /etc/hostname from the root mount is next.
	t.Setenv("HOST_PROC", filepath.Join(dir, "missing"))
	if got := hostHostname(); got != "gateway-etc" {
		t.Fatalf("want hostname from HOST_ROOT, got %q", got)
	}

	// No usable mounts: fall back to os.Hostname (whatever it is, non-empty
	// on any test host).
	t.Setenv("HOST_ROOT", filepath.Join(dir, "missing"))
	own, _ := os.Hostname()
	if got := hostHostname(); got != own {
		t.Fatalf("want os.Hostname fallback %q, got %q", own, got)
	}
}

func TestFromEnvNodeNameOverride(t *testing.T) {
	t.Setenv("BIFROST_AGENT_HUB_URL", "http://hub:8000")
	t.Setenv("BIFROST_AGENT_ENROLL_TOKEN", "tok")
	t.Setenv("BIFROST_AGENT_NODE_NAME", "mi-nas")
	cfg, err := FromEnv()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.NodeName != "mi-nas" {
		t.Fatalf("explicit BIFROST_AGENT_NODE_NAME must win, got %q", cfg.NodeName)
	}
}
