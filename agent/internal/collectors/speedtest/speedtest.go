// Package speedtest measures WAN latency and throughput from the node using
// Cloudflare's speed endpoints — stdlib only, no external binaries.
package speedtest

import (
	"context"
	"io"
	"math"
	"net/http"
	"sync/atomic"
	"time"
)

const (
	base          = "https://speed.cloudflare.com"
	phaseDuration = 8 * time.Second
)

func get(ctx context.Context, client *http.Client, url string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, err = io.Copy(io.Discard, resp.Body)
	return err
}

// Run returns (latencyMs, downloadMbps, uploadMbps). Each throughput phase
// reads or writes for up to phaseDuration; partial phases still measure.
func Run(ctx context.Context) (float64, float64, float64, error) {
	client := &http.Client{}

	// Warm up the connection, then take the best of three tiny round trips.
	if err := get(ctx, client, base+"/__down?bytes=0"); err != nil {
		return 0, 0, 0, err
	}
	latency := math.MaxFloat64
	for range 3 {
		start := time.Now()
		if err := get(ctx, client, base+"/__down?bytes=0"); err != nil {
			return 0, 0, 0, err
		}
		if ms := float64(time.Since(start).Microseconds()) / 1000; ms < latency {
			latency = ms
		}
	}

	// Download: 100MB requests back to back until the window closes — the
	// endpoint caps single responses, so one huge request just errors small.
	downCtx, cancelDown := context.WithTimeout(ctx, phaseDuration)
	defer cancelDown()
	var received int64
	start := time.Now()
	for downCtx.Err() == nil {
		req, derr := http.NewRequestWithContext(
			downCtx, http.MethodGet, base+"/__down?bytes=104857600", nil,
		)
		if derr != nil {
			return 0, 0, 0, derr
		}
		resp, derr := client.Do(req)
		if derr != nil {
			break // deadline cut is expected
		}
		n, _ := io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			break
		}
		received += n
	}
	downMbps := float64(received) * 8 / time.Since(start).Seconds() / 1e6

	// Upload: stream zeros until the window closes.
	upCtx, cancelUp := context.WithTimeout(ctx, phaseDuration)
	defer cancelUp()
	var sent atomic.Int64
	reader, writer := io.Pipe()
	go func() {
		chunk := make([]byte, 64*1024)
		for upCtx.Err() == nil {
			n, werr := writer.Write(chunk)
			sent.Add(int64(n))
			if werr != nil {
				return
			}
		}
		writer.Close()
	}()
	upReq, err := http.NewRequestWithContext(upCtx, http.MethodPost, base+"/__up", reader)
	if err != nil {
		return 0, 0, 0, err
	}
	start = time.Now()
	upResp, upErr := client.Do(upReq)
	elapsed := time.Since(start).Seconds()
	if upErr == nil {
		io.Copy(io.Discard, upResp.Body)
		upResp.Body.Close()
	}
	upMbps := 0.0
	if elapsed > 0 && sent.Load() > 0 {
		upMbps = float64(sent.Load()) * 8 / elapsed / 1e6
	}
	return latency, downMbps, upMbps, nil
}
