package config

import (
	"os"
	"path/filepath"
	"testing"
)

// Regression: inside Docker, os.Hostname() is the container id — and
// /proc/sys/kernel/hostname is no way out (procfs answers with the READER's
// UTS namespace, so a host /proc mount still returns the container's name;
// verified against a real docker run). The host's /etc/hostname under
// HOST_ROOT is the reliable source.
func TestHostHostnameReadsHostRootEtcHostname(t *testing.T) {
	dir := t.TempDir()
	root := filepath.Join(dir, "rootfs")
	if err := os.MkdirAll(filepath.Join(root, "etc"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "etc/hostname"), []byte("gateway\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("HOST_ROOT", root)
	if got := hostHostname(); got != "gateway" {
		t.Fatalf("want hostname from HOST_ROOT/etc/hostname, got %q", got)
	}

	// No usable mount: fall back to os.Hostname (correct under uts: host).
	t.Setenv("HOST_ROOT", filepath.Join(dir, "missing"))
	own, _ := os.Hostname()
	if got := hostHostname(); got != own {
		t.Fatalf("want os.Hostname fallback %q, got %q", own, got)
	}

	// An empty /etc/hostname must not win over the fallback.
	empty := filepath.Join(dir, "empty-root")
	if err := os.MkdirAll(filepath.Join(empty, "etc"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(empty, "etc/hostname"), []byte("\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("HOST_ROOT", empty)
	if got := hostHostname(); got != own {
		t.Fatalf("empty /etc/hostname must fall back to %q, got %q", own, got)
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
