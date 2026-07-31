package fs

import (
	"context"
	"testing"
)

func TestRelevantMount(t *testing.T) {
	cases := []struct {
		mountpoint, fstype string
		want               bool
	}{
		{"/", "ext4", true},
		{"/mnt/nas", "nfs4", true},
		{"/srv/media", "nfs", true},
		{"/data", "btrfs", true},
		{"/proc", "proc", false},
		{"/sys/fs/cgroup", "cgroup2", false},
		{"/tmp", "tmpfs", false},
		{"/var/lib/docker/overlay2/x", "ext4", false},
		{"/run/user/1000", "ext4", false},
		{"/snap/core/123", "squashfs", false},
	}
	for _, c := range cases {
		if got := relevantMount(c.mountpoint, c.fstype); got != c.want {
			t.Errorf("relevantMount(%q, %q) = %v, want %v", c.mountpoint, c.fstype, got, c.want)
		}
	}
}

func TestCollectSmoke(t *testing.T) {
	// Runs against whatever environment hosts the tests (bare metal or a
	// build container): every reported mount must be plausible and no
	// pseudo-filesystem may leak through the filter.
	mounts := New().Collect(context.Background())
	if len(mounts) == 0 {
		t.Skip("no visible filesystems in this environment")
	}
	for _, m := range mounts {
		if skipFstypes[m.Fstype] {
			t.Errorf("pseudo filesystem leaked: %+v", m)
		}
		if !m.Stale && (m.TotalBytes <= 0 || m.UsedBytes < 0 || m.UsedBytes > m.TotalBytes) {
			t.Errorf("implausible mount: %+v", m)
		}
	}
}
