package system

import (
	"crypto/sha256"
	"encoding/hex"
	"net"
	"os"
	"sort"
	"strings"
)

// Fingerprint identifies the host across agent container recreations:
// sha256 of /etc/machine-id (bind-mounted from the host), then the DMI
// product UUID (host-stable, readable through the HOST_SYS mount), and only
// then hostname + sorted MAC addresses. The MAC fallback is unstable inside
// Docker (the container NIC gets a fresh random MAC per start), so real
// deployments should always mount /etc/machine-id or /sys.
func Fingerprint() string {
	for _, path := range identityPaths() {
		if raw, err := os.ReadFile(path); err == nil {
			if id := strings.TrimSpace(string(raw)); id != "" {
				return hashHex(id)
			}
		}
	}
	return hashHex(fallbackIdentity())
}

func identityPaths() []string {
	paths := []string{}
	if root := os.Getenv("HOST_ROOT"); root != "" {
		paths = append(paths, root+"/etc/machine-id")
	}
	paths = append(paths, "/etc/machine-id")
	if sys := os.Getenv("HOST_SYS"); sys != "" {
		paths = append(paths, sys+"/class/dmi/id/product_uuid")
	}
	return append(paths, "/sys/class/dmi/id/product_uuid")
}

func fallbackIdentity() string {
	hostname, _ := os.Hostname()
	macs := []string{}
	if ifaces, err := net.Interfaces(); err == nil {
		for _, iface := range ifaces {
			if mac := iface.HardwareAddr.String(); mac != "" {
				macs = append(macs, mac)
			}
		}
	}
	sort.Strings(macs)
	return hostname + "|" + strings.Join(macs, ",")
}

func hashHex(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}
