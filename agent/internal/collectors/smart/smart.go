// Package smart reads disk health via smartmontools' JSON output
// (`smartctl --scan --json` + `smartctl -a -j <dev>`), which normalizes
// SATA/NVMe/USB-bridge quirks for us.
package smart

import (
	"context"
	"encoding/json"
	"os/exec"
	"sort"
	"time"

	"github.com/zurdi15/bifrost/agent/internal/protocol"
)

const commandTimeout = 30 * time.Second

type Collector struct {
	binary string
}

func New() *Collector {
	return &Collector{binary: "smartctl"}
}

// Available reports whether smartctl exists and sees at least one device
// (requires the container to run with disk device access).
func (c *Collector) Available(ctx context.Context) bool {
	return len(c.scan(ctx)) > 0
}

type scanEntry struct {
	Name string `json:"name"`
	Type string `json:"type"`
}

func (c *Collector) scan(ctx context.Context) []scanEntry {
	ctx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()
	out, err := exec.CommandContext(ctx, c.binary, "--scan", "--json").Output()
	if err != nil {
		return nil
	}
	var parsed struct {
		Devices []scanEntry `json:"devices"`
	}
	if json.Unmarshal(out, &parsed) != nil {
		return nil
	}
	return parsed.Devices
}

// Collect queries every scanned device. smartctl exits non-zero for failing
// disks while still printing full JSON, so output is parsed regardless.
func (c *Collector) Collect(ctx context.Context) []protocol.SmartDisk {
	devices := c.scan(ctx)
	disks := make([]protocol.SmartDisk, 0, len(devices))
	for _, device := range devices {
		cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
		out, _ := exec.CommandContext(
			cmdCtx, c.binary, "-a", "-j", "-d", device.Type, device.Name,
		).Output()
		cancel()
		if len(out) == 0 {
			continue
		}
		if disk, ok := ParseSmartctl(device.Name, out); ok {
			disks = append(disks, disk)
		}
	}
	sort.Slice(disks, func(i, j int) bool { return disks[i].Device < disks[j].Device })
	return disks
}

// smartctlOutput is the subset of `smartctl -a -j` we consume.
type smartctlOutput struct {
	Device struct {
		Protocol string `json:"protocol"`
	} `json:"device"`
	ModelName    string `json:"model_name"`
	SerialNumber string `json:"serial_number"`
	RotationRate int    `json:"rotation_rate"`
	UserCapacity struct {
		Bytes int64 `json:"bytes"`
	} `json:"user_capacity"`
	SmartStatus *struct {
		Passed bool `json:"passed"`
	} `json:"smart_status"`
	Temperature struct {
		Current float64 `json:"current"`
	} `json:"temperature"`
	PowerOnTime struct {
		Hours int64 `json:"hours"`
	} `json:"power_on_time"`
	AtaSmartAttributes *struct {
		Table []struct {
			ID  int `json:"id"`
			Raw struct {
				Value int64 `json:"value"`
			} `json:"raw"`
		} `json:"table"`
	} `json:"ata_smart_attributes"`
	NvmeSmartHealthInformationLog *struct {
		PercentageUsed float64 `json:"percentage_used"`
	} `json:"nvme_smart_health_information_log"`
}

func ParseSmartctl(device string, raw []byte) (protocol.SmartDisk, bool) {
	var out smartctlOutput
	if err := json.Unmarshal(raw, &out); err != nil {
		return protocol.SmartDisk{}, false
	}
	if out.ModelName == "" && out.SerialNumber == "" {
		return protocol.SmartDisk{}, false // no access / not a disk
	}

	disk := protocol.SmartDisk{
		Device:        device,
		Model:         out.ModelName,
		Serial:        out.SerialNumber,
		CapacityBytes: out.UserCapacity.Bytes,
		SmartStatus:   "unknown",
		RawJSON:       string(raw),
	}
	switch {
	case out.Device.Protocol == "NVMe":
		disk.Kind = "nvme"
	case out.RotationRate > 0:
		disk.Kind = "hdd"
	default:
		disk.Kind = "ssd"
	}
	if out.SmartStatus != nil {
		if out.SmartStatus.Passed {
			disk.SmartStatus = "passed"
		} else {
			disk.SmartStatus = "failed"
		}
	}
	if out.Temperature.Current > 0 {
		temp := out.Temperature.Current
		disk.TempC = &temp
	}
	if out.PowerOnTime.Hours > 0 {
		hours := out.PowerOnTime.Hours
		disk.PowerOnHours = &hours
	}
	if out.AtaSmartAttributes != nil {
		for _, attr := range out.AtaSmartAttributes.Table {
			value := attr.Raw.Value
			switch attr.ID {
			case 5: // Reallocated_Sector_Ct
				disk.ReallocSectors = &value
			case 197: // Current_Pending_Sector
				disk.PendingSectors = &value
			}
		}
	}
	if out.NvmeSmartHealthInformationLog != nil {
		wear := out.NvmeSmartHealthInformationLog.PercentageUsed
		disk.WearPct = &wear
	}
	return disk, true
}
