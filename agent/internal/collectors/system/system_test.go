package system

import (
	"context"
	"os"
	"path/filepath"
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

// Regression: a single unreadable sensor (a powered-down iwlwifi hwmon reads
// empty, exactly as seen on real hardware) makes gopsutil return the good
// sensors ALONGSIDE a warnings error. Bailing on that error dropped the CPU
// temperature entirely on any machine with one flaky sensor.
func TestCollectTempsSurvivesBrokenSensor(t *testing.T) {
	sys := t.TempDir()
	write := func(path, content string) {
		t.Helper()
		full := filepath.Join(sys, path)
		if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write("class/hwmon/hwmon0/name", "iwlwifi_1\n")
	write("class/hwmon/hwmon0/temp1_input", "") // sleeping wifi: empty read
	write("class/hwmon/hwmon1/name", "coretemp\n")
	write("class/hwmon/hwmon1/temp1_label", "Package id 0\n")
	write("class/hwmon/hwmon1/temp1_input", "84000\n")
	t.Setenv("HOST_SYS", sys)

	samples := map[string]float64{}
	New().collectTemps(context.Background(), func(name string, value float64) {
		samples[name] = value
	})
	if samples["temp.cpu"] != 84.0 {
		t.Fatalf("want temp.cpu=84.0 despite the broken sensor, got %v", samples)
	}
}

// Regression: stripped NAS kernels (TerraMaster TOS, as seen on a real F2
// unit) expose a single acpitz thermal zone and nothing else — no coretemp,
// no k10temp. temp.cpu must fall back to it, but never shadow a real CPU
// sensor when one exists.
func TestCollectTempsAcpitzFallback(t *testing.T) {
	writeTo := func(sys, path, content string) {
		t.Helper()
		full := filepath.Join(sys, path)
		if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	collect := func(sys string) map[string]float64 {
		t.Setenv("HOST_SYS", sys)
		samples := map[string]float64{}
		New().collectTemps(context.Background(), func(name string, value float64) {
			samples[name] = value
		})
		return samples
	}

	acpitzOnly := t.TempDir()
	writeTo(acpitzOnly, "class/hwmon/hwmon0/name", "acpitz\n")
	writeTo(acpitzOnly, "class/hwmon/hwmon0/temp1_input", "27800\n")
	if samples := collect(acpitzOnly); samples["temp.cpu"] != 27.8 {
		t.Fatalf("want temp.cpu=27.8 from the acpitz fallback, got %v", samples)
	}

	withCoretemp := t.TempDir()
	writeTo(withCoretemp, "class/hwmon/hwmon0/name", "acpitz\n")
	writeTo(withCoretemp, "class/hwmon/hwmon0/temp1_input", "27800\n")
	writeTo(withCoretemp, "class/hwmon/hwmon1/name", "coretemp\n")
	writeTo(withCoretemp, "class/hwmon/hwmon1/temp1_label", "Package id 0\n")
	writeTo(withCoretemp, "class/hwmon/hwmon1/temp1_input", "84000\n")
	if samples := collect(withCoretemp); samples["temp.cpu"] != 84.0 {
		t.Fatalf("want the real CPU sensor to win over acpitz, got %v", samples)
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
