package transport

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/zurdi15/bifrost/agent/internal/protocol"
)

// fakeHub is a minimal hub-side implementation for exercising the client.
type fakeHub struct {
	mu        sync.Mutex
	metrics   []protocol.Metrics
	conns     int
	resume    uint64
	ackAfter  int // send an ack after this many metrics (0 = never)
	dropAfter int // close the connection after this many metrics (0 = never)
}

func (h *fakeHub) handler(t *testing.T) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") == "" || r.Header.Get("X-Bifrost-Fingerprint") == "" {
			t.Error("missing auth headers")
		}
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")
		ctx := r.Context()

		_, raw, err := conn.Read(ctx) // hello
		if err != nil {
			return
		}
		if msgType, _ := protocol.MessageType(raw); msgType != "hello" {
			t.Errorf("first message = %q, want hello", msgType)
			return
		}
		var hello protocol.Hello
		_ = json.Unmarshal(raw, &hello)

		h.mu.Lock()
		h.conns++
		// Mirror hub semantics: a fresh agent (low start_seq) resets our position.
		if hello.StartSeq < h.resume {
			h.resume = hello.StartSeq
		}
		resume := h.resume
		h.mu.Unlock()

		ack := protocol.HelloAck{
			T: "hello_ack", Proto: protocol.Version, NodeUUID: "node-1",
			AgentToken:    "per-agent-token",
			Config:        protocol.AgentConfig{MetricsIntervalS: 1, HeartbeatIntervalS: 60},
			ResumeFromSeq: resume,
		}
		payload, _ := json.Marshal(ack)
		if err := conn.Write(ctx, websocket.MessageText, payload); err != nil {
			return
		}

		received := 0
		for {
			_, raw, err := conn.Read(ctx)
			if err != nil {
				return
			}
			msgType, _ := protocol.MessageType(raw)
			if msgType != "metrics" {
				continue
			}
			var m protocol.Metrics
			_ = json.Unmarshal(raw, &m)
			h.mu.Lock()
			h.metrics = append(h.metrics, m)
			h.resume = m.Seq
			h.mu.Unlock()
			received++
			if h.ackAfter > 0 && received%h.ackAfter == 0 {
				out, _ := json.Marshal(protocol.Ack{T: "ack", UptoSeq: m.Seq})
				_ = conn.Write(ctx, websocket.MessageText, out)
			}
			if h.dropAfter > 0 && received >= h.dropAfter {
				return // simulate hub crash
			}
		}
	}
}

func startClient(t *testing.T, url string) (*Client, context.CancelFunc) {
	hello := protocol.NewHello("test", "unit", "linux", "amd64", 0, []string{"system"})
	client, err := NewClient(url, "enroll-token", "fp-test", hello)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	go client.Run(ctx)
	return client, cancel
}

func waitFor(t *testing.T, timeout time.Duration, cond func() bool) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("condition not met in time")
}

func TestClientHandshakeAndMetrics(t *testing.T) {
	hub := &fakeHub{ackAfter: 1}
	server := httptest.NewServer(hub.handler(t))
	defer server.Close()

	client, cancel := startClient(t, server.URL)
	defer cancel()

	client.Out <- protocol.NewMetrics(0, []protocol.Sample{{Name: "cpu.pct", Value: 12.0}})
	client.Out <- protocol.NewMetrics(0, []protocol.Sample{{Name: "cpu.pct", Value: 34.0}})

	waitFor(t, 3*time.Second, func() bool {
		hub.mu.Lock()
		defer hub.mu.Unlock()
		return len(hub.metrics) == 2
	})

	hub.mu.Lock()
	defer hub.mu.Unlock()
	if hub.metrics[0].Seq != 1 || hub.metrics[1].Seq != 2 {
		t.Fatalf("seqs = %d,%d want 1,2", hub.metrics[0].Seq, hub.metrics[1].Seq)
	}
	if hub.metrics[1].Samples[0].Value != 34.0 {
		t.Fatalf("unexpected sample: %+v", hub.metrics[1])
	}
	waitFor(t, time.Second, func() bool { return client.ring.Len() == 0 }) // acks trimmed
}

func TestClientResumesAfterDrop(t *testing.T) {
	// The hub never acks and drops the connection after the first metric:
	// the client must reconnect and resend everything past resume_from_seq.
	hub := &fakeHub{dropAfter: 1}
	server := httptest.NewServer(hub.handler(t))
	defer server.Close()

	client, cancel := startClient(t, server.URL)
	defer cancel()

	client.Out <- protocol.NewMetrics(0, []protocol.Sample{{Name: "a", Value: 1}})
	waitFor(t, 3*time.Second, func() bool {
		hub.mu.Lock()
		defer hub.mu.Unlock()
		return len(hub.metrics) == 1 // first delivery, then the hub drops us
	})

	hub.mu.Lock()
	hub.dropAfter = 0 // behave from now on
	hub.mu.Unlock()

	// Queued while disconnected; must arrive after the automatic reconnect.
	client.Out <- protocol.NewMetrics(0, []protocol.Sample{{Name: "b", Value: 2}})

	waitFor(t, 10*time.Second, func() bool {
		hub.mu.Lock()
		defer hub.mu.Unlock()
		return len(hub.metrics) >= 2 && hub.conns >= 2
	})

	hub.mu.Lock()
	defer hub.mu.Unlock()
	last := hub.metrics[len(hub.metrics)-1]
	if last.Samples[0].Name != "b" {
		t.Fatalf("expected queued frame after resume, got %+v", last)
	}
}

func TestFreshProcessResetsHubPosition(t *testing.T) {
	// Regression: hub remembers last_seq=12 from a previous agent process; a
	// restarted (stateless) agent declares start_seq=0 in hello, the hub
	// resets its dedup position, and seq 1 flows instead of being dropped.
	hub := &fakeHub{resume: 12, ackAfter: 1}
	server := httptest.NewServer(hub.handler(t))
	defer server.Close()

	client, cancel := startClient(t, server.URL)
	defer cancel()

	client.Out <- protocol.NewMetrics(0, []protocol.Sample{{Name: "cpu.pct", Value: 1}})
	waitFor(t, 3*time.Second, func() bool {
		hub.mu.Lock()
		defer hub.mu.Unlock()
		return len(hub.metrics) == 1
	})
	hub.mu.Lock()
	defer hub.mu.Unlock()
	if hub.metrics[0].Seq != 1 {
		t.Fatalf("seq = %d, want 1 (hub position reset by start_seq=0)", hub.metrics[0].Seq)
	}
}

func TestToWsURL(t *testing.T) {
	cases := map[string]string{
		"http://hub:8000":   "ws://hub:8000/api/ws/agent",
		"https://hub.tld":   "wss://hub.tld/api/ws/agent",
		"https://hub.tld/":  "wss://hub.tld/api/ws/agent",
		"ws://already:8000": "ws://already:8000/api/ws/agent",
	}
	for in, want := range cases {
		got, err := toWsURL(in)
		if err != nil || got != want {
			t.Errorf("toWsURL(%q) = %q, %v; want %q", in, got, err, want)
		}
	}
	if _, err := toWsURL("ftp://nope"); err == nil {
		t.Error("expected error for unsupported scheme")
	}
}
