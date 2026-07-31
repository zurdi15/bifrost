package dockermon

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

const listFixture = `[
  {
    "Id": "abc123def456abc123def456",
    "Names": ["/romm"],
    "Image": "ghcr.io/rommapp/romm:4.6",
    "State": "running",
    "Status": "Up 3 hours (healthy)",
    "Created": 1700000000,
    "Labels": {"bifrost.url": "https://romm.example", "bifrost.group": "media"},
    "Ports": [
      {"IP": "0.0.0.0", "PrivatePort": 8080, "PublicPort": 8085, "Type": "tcp"},
      {"IP": "::", "PrivatePort": 8080, "PublicPort": 8085, "Type": "tcp"}
    ]
  },
  {
    "Id": "ffff0000ffff0000",
    "Names": ["/pihole"],
    "Image": "pihole/pihole:latest",
    "State": "exited",
    "Status": "Exited (0) 2 days ago",
    "Created": 1690000000,
    "Labels": {},
    "Ports": [{"PrivatePort": 53, "Type": "udp"}]
  }
]`

func newTestClient(t *testing.T, handler http.HandlerFunc) *Client {
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	return NewForURL(server.URL)
}

func TestListParsesContainers(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/containers/json" {
			t.Errorf("unexpected path %s", r.URL.Path)
		}
		if r.URL.Query().Get("all") != "1" {
			t.Error("expected all=1 (stopped containers matter)")
		}
		w.Write([]byte(listFixture))
	})

	containers, err := client.List(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(containers) != 2 {
		t.Fatalf("got %d containers, want 2", len(containers))
	}
	// Sorted by name: pihole first.
	pihole, romm := containers[0], containers[1]

	if romm.Name != "romm" || romm.State != "running" || romm.Health != "healthy" {
		t.Fatalf("romm parse wrong: %+v", romm)
	}
	if romm.Labels["bifrost.url"] != "https://romm.example" {
		t.Fatalf("labels lost: %+v", romm.Labels)
	}
	// Dual-stack duplicate port collapsed.
	if len(romm.Ports) != 1 || romm.Ports[0] != "8085:8080/tcp" {
		t.Fatalf("ports wrong: %v", romm.Ports)
	}

	if pihole.Health != "" || pihole.State != "exited" {
		t.Fatalf("pihole parse wrong: %+v", pihole)
	}
	if len(pihole.Ports) != 1 || pihole.Ports[0] != "53/udp" {
		t.Fatalf("unpublished port wrong: %v", pihole.Ports)
	}
}

func TestEventsStreamFiltersAndNormalizes(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		// exec_create noise must be filtered; health_status normalized.
		w.Write([]byte(`{"Action":"exec_create: sh","id":"x","Actor":{"Attributes":{"name":"noise"}}}
{"Action":"start","id":"abc","Actor":{"Attributes":{"name":"romm","image":"ghcr.io/rommapp/romm"}}}
{"Action":"health_status: unhealthy","id":"abc","Actor":{"Attributes":{"name":"romm"}}}
`))
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	events := make(chan Event, 8)
	done := make(chan error, 1)
	go func() { done <- client.Events(ctx, events) }()

	first := <-events
	if first.Action != "start" || first.Name != "romm" || first.Image != "ghcr.io/rommapp/romm" {
		t.Fatalf("first event wrong: %+v", first)
	}
	second := <-events
	if second.Action != "health_status" {
		t.Fatalf("health_status not normalized: %+v", second)
	}
	<-done // stream ends on EOF
}

func TestAvailableFalseWhenNoDaemon(t *testing.T) {
	client := New("/nonexistent/docker.sock")
	if client.Available(context.Background()) {
		t.Fatal("expected unavailable")
	}
}
