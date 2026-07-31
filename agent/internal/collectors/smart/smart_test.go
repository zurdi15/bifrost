package smart

import "testing"

const ataFixture = `{
  "device": {"name": "/dev/sda", "type": "sat", "protocol": "ATA"},
  "model_name": "WDC WD80EFAX-68KNBN0",
  "serial_number": "VAG12345",
  "rotation_rate": 5400,
  "user_capacity": {"bytes": 8001563222016},
  "smart_status": {"passed": true},
  "temperature": {"current": 38},
  "power_on_time": {"hours": 21504},
  "ata_smart_attributes": {"table": [
    {"id": 5, "name": "Reallocated_Sector_Ct", "raw": {"value": 0}},
    {"id": 194, "name": "Temperature_Celsius", "raw": {"value": 38}},
    {"id": 197, "name": "Current_Pending_Sector", "raw": {"value": 3}}
  ]}
}`

const nvmeFixture = `{
  "device": {"name": "/dev/nvme0", "type": "nvme", "protocol": "NVMe"},
  "model_name": "Samsung SSD 980 PRO 1TB",
  "serial_number": "S5GXNX0T123",
  "user_capacity": {"bytes": 1000204886016},
  "smart_status": {"passed": false},
  "temperature": {"current": 52},
  "power_on_time": {"hours": 8760},
  "nvme_smart_health_information_log": {"percentage_used": 7}
}`

func TestParseAtaHdd(t *testing.T) {
	disk, ok := ParseSmartctl("/dev/sda", []byte(ataFixture))
	if !ok {
		t.Fatal("parse failed")
	}
	if disk.Kind != "hdd" || disk.Model != "WDC WD80EFAX-68KNBN0" || disk.Serial != "VAG12345" {
		t.Fatalf("identity wrong: %+v", disk)
	}
	if disk.SmartStatus != "passed" || *disk.TempC != 38 || *disk.PowerOnHours != 21504 {
		t.Fatalf("health wrong: %+v", disk)
	}
	if *disk.ReallocSectors != 0 || *disk.PendingSectors != 3 {
		t.Fatalf("sector attributes wrong: %+v", disk)
	}
	if disk.CapacityBytes != 8001563222016 {
		t.Fatalf("capacity wrong: %d", disk.CapacityBytes)
	}
}

func TestParseNvmeFailing(t *testing.T) {
	disk, ok := ParseSmartctl("/dev/nvme0", []byte(nvmeFixture))
	if !ok {
		t.Fatal("parse failed")
	}
	if disk.Kind != "nvme" || disk.SmartStatus != "failed" {
		t.Fatalf("nvme parse wrong: %+v", disk)
	}
	if *disk.WearPct != 7 {
		t.Fatalf("wear wrong: %+v", disk)
	}
	if disk.ReallocSectors != nil {
		t.Fatal("ata attributes must be absent on nvme")
	}
}

func TestParseInaccessibleDevice(t *testing.T) {
	if _, ok := ParseSmartctl("/dev/sdx", []byte(`{"smartctl":{"exit_status":2}}`)); ok {
		t.Fatal("expected not-ok for device without identity")
	}
	if _, ok := ParseSmartctl("/dev/sdx", []byte(`not json`)); ok {
		t.Fatal("expected not-ok for junk")
	}
}
