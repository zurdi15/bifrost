package transport

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"math/rand"
	"net/http"
	"strings"
	"sync/atomic"
	"time"

	"github.com/coder/websocket"

	"github.com/zurdi15/bifrost/agent/internal/protocol"
)

const (
	backoffBase = 1 * time.Second
	backoffCap  = 60 * time.Second
	ringSize    = 2048
)

var errPendingApproval = errors.New("node pending approval on the hub")

// Client owns the outbound WebSocket: it sequences and buffers data frames,
// resumes after reconnects, honors acks and live config pushes. It keeps no
// state on disk — a lost per-agent token simply re-enrolls by fingerprint.
type Client struct {
	wsURL       string
	enrollToken string
	fingerprint string
	hello       protocol.Hello

	ring       *Ring
	seq        atomic.Uint64
	agentToken atomic.Pointer[string]

	// Frames receives metric batches from collectors; the pump sequences and
	// rings them even while disconnected, so a hub outage loses nothing
	// (beyond the ring's graceful thinning).
	Frames chan []protocol.Sample
	notify chan struct{}

	// OnConfig fires on hello_ack and on live config pushes from the hub.
	OnConfig func(protocol.AgentConfig)

	heartbeatInterval atomic.Int64 // seconds
}

func NewClient(hubURL, enrollToken, fingerprint string, hello protocol.Hello) (*Client, error) {
	wsURL, err := toWsURL(hubURL)
	if err != nil {
		return nil, err
	}
	c := &Client{
		wsURL:       wsURL,
		enrollToken: enrollToken,
		fingerprint: fingerprint,
		hello:       hello,
		ring:        NewRing(ringSize),
		Frames:      make(chan []protocol.Sample, 64),
		notify:      make(chan struct{}, 1),
	}
	c.heartbeatInterval.Store(15)
	return c, nil
}

func toWsURL(hubURL string) (string, error) {
	switch {
	case strings.HasPrefix(hubURL, "http://"):
		hubURL = "ws://" + strings.TrimPrefix(hubURL, "http://")
	case strings.HasPrefix(hubURL, "https://"):
		hubURL = "wss://" + strings.TrimPrefix(hubURL, "https://")
	case strings.HasPrefix(hubURL, "ws://"), strings.HasPrefix(hubURL, "wss://"):
	default:
		return "", fmt.Errorf("hub url must be http(s):// or ws(s)://, got %q", hubURL)
	}
	return strings.TrimSuffix(hubURL, "/") + "/api/ws/agent", nil
}

// Run reconnects forever with jittered exponential backoff until ctx ends.
func (c *Client) Run(ctx context.Context) {
	go c.pump(ctx)
	backoff := backoffBase
	for {
		start := time.Now()
		err := c.session(ctx)
		if ctx.Err() != nil {
			return
		}
		if time.Since(start) > backoffCap {
			backoff = backoffBase // the session was healthy for a while
		}
		wait := backoff/2 + time.Duration(rand.Int63n(int64(backoff)/2+1))
		if errors.Is(err, errPendingApproval) {
			wait = backoffCap
			slog.Info("waiting for approval on the hub", "retry_in", wait)
		} else if err != nil {
			slog.Warn("hub connection lost", "err", err, "retry_in", wait)
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(wait):
		}
		if backoff < backoffCap {
			backoff *= 2
		}
	}
}

// pump drains collector frames into the ring regardless of connection state.
func (c *Client) pump(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		case samples := <-c.Frames:
			seq := c.seq.Add(1)
			frame, err := json.Marshal(protocol.NewMetrics(seq, time.Now().Unix(), samples))
			if err != nil {
				continue
			}
			c.ring.Push(seq, frame)
			select {
			case c.notify <- struct{}{}:
			default:
			}
		}
	}
}

func (c *Client) token() string {
	if t := c.agentToken.Load(); t != nil {
		return *t
	}
	return c.enrollToken
}

func (c *Client) session(ctx context.Context) error {
	headers := http.Header{}
	headers.Set("Authorization", "Bearer "+c.token())
	headers.Set("X-Bifrost-Fingerprint", c.fingerprint)

	dialCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
	conn, _, err := websocket.Dial(dialCtx, c.wsURL, &websocket.DialOptions{HTTPHeader: headers})
	cancel()
	if err != nil {
		// A stale per-agent token (hub wiped, node deleted) must not lock us
		// out forever: fall back to enrollment for the next attempt.
		if c.agentToken.Load() != nil {
			c.agentToken.Store(nil)
		}
		return fmt.Errorf("dial: %w", err)
	}
	defer conn.Close(websocket.StatusNormalClosure, "")
	conn.SetReadLimit(1 << 20)

	if err := c.writeJSON(ctx, conn, c.hello); err != nil {
		return fmt.Errorf("hello: %w", err)
	}

	ack, err := c.awaitHelloAck(ctx, conn)
	if err != nil {
		return err
	}
	if ack.AgentToken != "" {
		token := ack.AgentToken
		c.agentToken.Store(&token)
	}
	if ack.Config.HeartbeatIntervalS > 0 {
		c.heartbeatInterval.Store(int64(ack.Config.HeartbeatIntervalS))
	}
	if c.OnConfig != nil {
		c.OnConfig(ack.Config)
	}
	slog.Info("connected to hub", "node_uuid", ack.NodeUUID, "resume_from", ack.ResumeFromSeq)

	sent := ack.ResumeFromSeq
	flush := func() error {
		for _, entry := range c.ring.After(sent) {
			if err := conn.Write(ctx, websocket.MessageText, entry.Frame); err != nil {
				return err
			}
			sent = entry.Seq
		}
		return nil
	}
	if err := flush(); err != nil {
		return fmt.Errorf("resume: %w", err)
	}

	incoming := make(chan []byte, 8)
	readErr := make(chan error, 1)
	go func() {
		for {
			_, data, err := conn.Read(ctx)
			if err != nil {
				readErr <- err
				return
			}
			incoming <- data
		}
	}()

	heartbeat := time.NewTicker(time.Duration(c.heartbeatInterval.Load()) * time.Second)
	defer heartbeat.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case err := <-readErr:
			return err
		case <-c.notify:
			if err := flush(); err != nil {
				return err
			}
		case <-heartbeat.C:
			frame, _ := json.Marshal(protocol.NewHeartbeat(c.seq.Load(), time.Now().Unix()))
			if err := conn.Write(ctx, websocket.MessageText, frame); err != nil {
				return err
			}
		case data := <-incoming:
			if err := c.handleMessage(data); err != nil {
				return err
			}
		}
	}
}

func (c *Client) awaitHelloAck(ctx context.Context, conn *websocket.Conn) (*protocol.HelloAck, error) {
	readCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	_, data, err := conn.Read(readCtx)
	if err != nil {
		return nil, fmt.Errorf("await hello_ack: %w", err)
	}
	msgType, err := protocol.MessageType(data)
	if err != nil {
		return nil, err
	}
	switch msgType {
	case "hello_ack":
		var ack protocol.HelloAck
		if err := json.Unmarshal(data, &ack); err != nil {
			return nil, err
		}
		return &ack, nil
	case "error":
		var errMsg protocol.ErrorMsg
		_ = json.Unmarshal(data, &errMsg)
		switch errMsg.Code {
		case "pending_approval":
			return nil, errPendingApproval
		case "proto_unsupported":
			return nil, fmt.Errorf("hub rejected protocol v%d — upgrade the agent image: %s",
				protocol.Version, errMsg.Msg)
		default:
			return nil, fmt.Errorf("hub error %s: %s", errMsg.Code, errMsg.Msg)
		}
	default:
		return nil, fmt.Errorf("unexpected first message %q", msgType)
	}
}

func (c *Client) handleMessage(data []byte) error {
	msgType, err := protocol.MessageType(data)
	if err != nil {
		return nil // tolerate junk
	}
	switch msgType {
	case "ack":
		var ack protocol.Ack
		if json.Unmarshal(data, &ack) == nil {
			c.ring.AckUpTo(ack.UptoSeq)
		}
	case "config":
		var update protocol.ConfigUpdate
		if json.Unmarshal(data, &update) == nil {
			if update.Config.HeartbeatIntervalS > 0 {
				c.heartbeatInterval.Store(int64(update.Config.HeartbeatIntervalS))
			}
			if c.OnConfig != nil {
				c.OnConfig(update.Config)
			}
		}
	case "bye":
		return errors.New("hub said bye")
	case "error":
		var errMsg protocol.ErrorMsg
		_ = json.Unmarshal(data, &errMsg)
		return fmt.Errorf("hub error %s: %s", errMsg.Code, errMsg.Msg)
	case "resync":
		// Full-snapshot messages (containers, smart) arrive in later phases.
	}
	return nil
}

func (c *Client) writeJSON(ctx context.Context, conn *websocket.Conn, v any) error {
	data, err := json.Marshal(v)
	if err != nil {
		return err
	}
	writeCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	return conn.Write(writeCtx, websocket.MessageText, data)
}
