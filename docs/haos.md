# Home Assistant OS (design)

HAOS can't easily run arbitrary containers, so a HAOS box integrates at three levels:

1. **Monitored endpoint** (phase 6): register it as a `kind='endpoint'` node with a ping
   check and/or an HTTP check (e.g. `http://haos:8123/manifest.json`). Gives up/down and
   latency with zero footprint on the Pi.
2. **Home Assistant API widget** (phase 7): configure `url` + long-lived access token; the
   hub polls `/api/states` for chosen entities. With HA's *System Monitor* integration this
   surfaces CPU/memory/temperature/disk of the Pi itself.
3. **HAOS add-on** (future/community): HA add-ons are Docker containers with device access;
   an add-on `config.yaml` wrapping the `bifrost-agent` image (with `full_access`) would
   make it a full node. Not required for anything else to work.
