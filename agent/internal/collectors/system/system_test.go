package system

import (
	"context"
	"strings"
	"testing"
	"time"
)

func TestSanitize(t *testing.T) {
	cases := map[string]string{
		"eth0":                 "eth0",
		"Package id 0":         "package_id_0",
		"wlp3s0":               "wlp3s0",
		"weird/name with:sep":  "weird_name_with_sep",
		"UPPER.dots-dashes_ok": "upper.dots-dashes_ok",
	}
	for in, want := range cases {
		if got := sanitize(in); got != want {
			t.Errorf("sanitize(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestRound2(t *testing.T) {
	if round2(42.567) != 42.57 {
		t.Fatalf("round2(42.567) = %v", round2(42.567))
	}
	if round2(0) != 0 {
		t.Fatalf("round2(0) = %v", round2(0))
	}
}

func TestFingerprintIsStableHex(t *testing.T) {
	a, b := Fingerprint(), Fingerprint()
	if a != b {
		t.Fatal("fingerprint not stable across calls")
	}
	if len(a) != 64 || strings.ToLower(a) != a {
		t.Fatalf("fingerprint not sha256 hex: %q", a)
	}
}

func TestCollectSmoke(t *testing.T) {
	// Real collection against the running kernel: must produce at least the
	// core CPU/memory metrics on any Linux box.
	c := New()
	c.Collect(context.Background()) // prime rates
	time.Sleep(50 * time.Millisecond)
	samples := c.Collect(context.Background())

	names := map[string]bool{}
	for _, s := range samples {
		names[s.Name] = true
	}
	for _, want := range []string{"cpu.pct", "mem.total", "mem.used", "mem.pct"} {
		if !names[want] {
			t.Errorf("missing sample %q in %v", want, names)
		}
	}
}
