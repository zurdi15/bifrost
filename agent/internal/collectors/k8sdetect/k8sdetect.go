// Package k8sdetect looks for Kubernetes control planes on the host via
// well-known kubeconfig markers on the (read-only) host rootfs. The hub does
// the actual API watching; the agent only reports what exists here.
package k8sdetect

import (
	"crypto/sha256"
	"encoding/hex"
	"os"
	"regexp"

	"github.com/zurdi15/bifrost/agent/internal/protocol"
)

type marker struct {
	distro string
	path   string
}

var markers = []marker{
	{"k3s", "/etc/rancher/k3s/k3s.yaml"},
	{"kubeadm", "/etc/kubernetes/admin.conf"},
	{"k0s", "/var/lib/k0s/pki/admin.conf"},
}

var serverRe = regexp.MustCompile(`(?m)^\s*server:\s*(\S+)`)

// Detection carries what was found plus a fingerprint for change detection.
type Detection struct {
	Distro      string
	APIEndpoint string
	Kubeconfig  string
	Hash        string
}

// Detect scans the host rootfs for cluster markers. Returns nil when no
// cluster is present.
func Detect(hostRoot string) *Detection {
	for _, m := range markers {
		path := hostRoot + m.path
		info, err := os.Stat(path)
		if err != nil || info.IsDir() {
			continue
		}
		detection := &Detection{Distro: m.distro}
		// Reading may fail (0600 root-only without privileged) — the marker
		// existing is still worth reporting so the UI can ask for creds.
		if raw, err := os.ReadFile(path); err == nil {
			detection.Kubeconfig = string(raw)
			if match := serverRe.FindStringSubmatch(detection.Kubeconfig); match != nil {
				detection.APIEndpoint = match[1]
			}
		}
		sum := sha256.Sum256([]byte(detection.Distro + detection.APIEndpoint + detection.Kubeconfig))
		detection.Hash = hex.EncodeToString(sum[:])
		return detection
	}
	return nil
}

func (d *Detection) Message(ts int64) *protocol.K8sDetected {
	return protocol.NewK8sDetected(ts, d.Distro, d.APIEndpoint, d.Kubeconfig)
}
