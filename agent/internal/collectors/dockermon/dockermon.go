// Package dockermon discovers local containers by talking to the Docker
// Engine API directly over the unix socket — a ~150-line client instead of
// the full docker SDK dependency tree.
package dockermon

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/zurdi15/bifrost/agent/internal/protocol"
)

// Unversioned paths: the daemon serves its current API version, so the
// same client works against a 2019 NAS daemon and Docker 29 (which rejects
// pinned versions older than its supported minimum).

const DefaultSocket = "/var/run/docker.sock"

var healthRe = regexp.MustCompile(`\((healthy|unhealthy|health: starting)\)`)

type Client struct {
	httpc *http.Client
	base  string
}

// New builds a client for the unix socket at path.
func New(path string) *Client {
	return &Client{
		base: "http://docker",
		httpc: &http.Client{
			Transport: &http.Transport{
				DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
					var d net.Dialer
					return d.DialContext(ctx, "unix", path)
				},
			},
		},
	}
}

// NewForURL builds a client against an HTTP base (tests).
func NewForURL(base string) *Client {
	return &Client{base: strings.TrimSuffix(base, "/"), httpc: http.DefaultClient}
}

func (c *Client) Available(ctx context.Context) bool {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, c.base+"/version", nil)
	resp, err := c.httpc.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

// apiContainer is the subset of GET /containers/json we consume.
type apiContainer struct {
	ID      string            `json:"Id"`
	Names   []string          `json:"Names"`
	Image   string            `json:"Image"`
	State   string            `json:"State"`
	Status  string            `json:"Status"`
	Created int64             `json:"Created"`
	Labels  map[string]string `json:"Labels"`
	Ports   []struct {
		IP          string `json:"IP"`
		PrivatePort int    `json:"PrivatePort"`
		PublicPort  int    `json:"PublicPort"`
		Type        string `json:"Type"`
	} `json:"Ports"`
}

func (c *Client) List(ctx context.Context) ([]protocol.ContainerInfo, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.base+"/containers/json?all=1", nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("containers/json: HTTP %d", resp.StatusCode)
	}
	var raw []apiContainer
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return nil, err
	}
	out := make([]protocol.ContainerInfo, 0, len(raw))
	for _, ac := range raw {
		out = append(out, toInfo(ac))
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out, nil
}

func toInfo(ac apiContainer) protocol.ContainerInfo {
	name := ac.ID[:min(12, len(ac.ID))]
	if len(ac.Names) > 0 {
		name = strings.TrimPrefix(ac.Names[0], "/")
	}
	health := ""
	if m := healthRe.FindStringSubmatch(ac.Status); m != nil {
		health = strings.TrimPrefix(m[1], "health: ")
	}
	ports := make([]string, 0, len(ac.Ports))
	seen := map[string]bool{}
	for _, p := range ac.Ports {
		var s string
		if p.PublicPort > 0 {
			s = fmt.Sprintf("%d:%d/%s", p.PublicPort, p.PrivatePort, p.Type)
		} else {
			s = fmt.Sprintf("%d/%s", p.PrivatePort, p.Type)
		}
		if !seen[s] {
			seen[s] = true
			ports = append(ports, s)
		}
	}
	sort.Strings(ports)
	return protocol.ContainerInfo{
		ContainerID: ac.ID,
		Name:        name,
		Image:       ac.Image,
		State:       ac.State,
		Health:      health,
		Ports:       ports,
		Labels:      ac.Labels,
		StartedAt:   ac.Created,
	}
}

// Event is a docker container lifecycle event.
type Event struct {
	Action string
	ID     string
	Name   string
	Image  string
}

var interestingActions = map[string]bool{
	"start": true, "die": true, "stop": true, "kill": true, "restart": true,
	"pause": true, "unpause": true, "destroy": true, "create": true, "rename": true,
}

// Events streams container lifecycle events until ctx ends or the stream
// breaks (caller reconnects).
func (c *Client) Events(ctx context.Context, out chan<- Event) error {
	filters := url.QueryEscape(`{"type":["container"]}`)
	req, err := http.NewRequestWithContext(
		ctx, http.MethodGet, c.base+"/events?filters="+filters, nil,
	)
	if err != nil {
		return err
	}
	resp, err := c.httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("events: HTTP %d", resp.StatusCode)
	}
	dec := json.NewDecoder(resp.Body)
	for {
		var raw struct {
			Action string `json:"Action"`
			ID     string `json:"id"`
			Actor  struct {
				Attributes map[string]string `json:"Attributes"`
			} `json:"Actor"`
		}
		if err := dec.Decode(&raw); err != nil {
			return err
		}
		action := raw.Action
		// health_status events arrive as "health_status: healthy".
		if strings.HasPrefix(action, "health_status") {
			action = "health_status"
		} else if !interestingActions[action] {
			continue
		}
		select {
		case out <- Event{
			Action: action,
			ID:     raw.ID,
			Name:   raw.Actor.Attributes["name"],
			Image:  raw.Actor.Attributes["image"],
		}:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
}
