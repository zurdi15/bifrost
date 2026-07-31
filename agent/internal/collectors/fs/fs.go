// Package fs snapshots host filesystem usage. Each statfs runs with a
// timeout so a hung NFS mount marks itself stale instead of blocking the
// collection loop forever.
package fs

import (
	"context"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/shirou/gopsutil/v4/disk"

	"github.com/zurdi15/bifrost/agent/internal/protocol"
)

const statfsTimeout = 5 * time.Second

// Pseudo/ephemeral filesystems that never matter on a dashboard.
var skipFstypes = map[string]bool{
	"proc": true, "sysfs": true, "devtmpfs": true, "devpts": true, "tmpfs": true,
	"cgroup": true, "cgroup2": true, "overlay": true, "squashfs": true, "ramfs": true,
	"autofs": true, "mqueue": true, "hugetlbfs": true, "debugfs": true, "tracefs": true,
	"securityfs": true, "pstore": true, "bpf": true, "configfs": true, "fusectl": true,
	"binfmt_misc": true, "nsfs": true, "efivarfs": true, "fuse.portal": true,
}

var skipPrefixes = []string{
	"/var/lib/docker/", "/var/lib/kubelet/", "/run/", "/snap/", "/boot/efi",
}

func relevantMount(mountpoint, fstype string) bool {
	if skipFstypes[fstype] {
		return false
	}
	for _, prefix := range skipPrefixes {
		if strings.HasPrefix(mountpoint, prefix) {
			return false
		}
	}
	return true
}

type Collector struct {
	hostRoot string
}

func New() *Collector {
	return &Collector{hostRoot: os.Getenv("HOST_ROOT")}
}

// Collect returns the current mount snapshot. NFS/network mounts that do not
// answer statfs within the timeout are reported with stale=true.
func (c *Collector) Collect(ctx context.Context) []protocol.FsMountInfo {
	partitions, err := disk.PartitionsWithContext(ctx, false)
	if err != nil {
		return nil
	}
	out := make([]protocol.FsMountInfo, 0, len(partitions))
	seen := map[string]bool{}
	for _, p := range partitions {
		if !relevantMount(p.Mountpoint, p.Fstype) || seen[p.Mountpoint] {
			continue
		}
		seen[p.Mountpoint] = true
		info := protocol.FsMountInfo{
			Mountpoint: p.Mountpoint,
			Device:     p.Device,
			Fstype:     p.Fstype,
		}
		// The host's mounts live under HOST_ROOT from our namespace.
		statPath := c.hostRoot + p.Mountpoint
		if usage, ok := usageWithTimeout(ctx, statPath); ok {
			info.TotalBytes = int64(usage.Total)
			info.UsedBytes = int64(usage.Used)
		} else {
			info.Stale = true
		}
		out = append(out, info)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Mountpoint < out[j].Mountpoint })
	return out
}

func usageWithTimeout(ctx context.Context, path string) (*disk.UsageStat, bool) {
	type result struct {
		usage *disk.UsageStat
		err   error
	}
	ch := make(chan result, 1)
	go func() {
		usage, err := disk.Usage(path)
		ch <- result{usage, err}
	}()
	select {
	case r := <-ch:
		return r.usage, r.err == nil && r.usage != nil && r.usage.Total > 0
	case <-time.After(statfsTimeout):
		return nil, false // hung mount: the goroutine leaks until statfs returns
	case <-ctx.Done():
		return nil, false
	}
}
