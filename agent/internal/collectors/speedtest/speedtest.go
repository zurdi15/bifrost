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

func timedDownload(ctx context.Context, client *http.Client, url string) (int64, float64) {
	reqCtx, cancel := context.WithTimeout(ctx, phaseDuration)
	defer cancel()
	req, err := http.NewRequestWithContext(reqCtx, http.MethodGet, url, nil)
	if err != nil {
		return 0, 0
	}
	start := time.Now()
	resp, err := client.Do(req)
	if err != nil {
		return 0, 0
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return 0, 0
	}
	n, _ := io.Copy(io.Discard, resp.Body) // deadline cut is expected
	return n, time.Since(start).Seconds()
}

func readOnce(ctx context.Context, client *http.Client, url string) (int64, bool) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return 0, false
	}
	resp, err := client.Do(req)
	if err != nil {
		return 0, false
	}
	defer resp.Body.Close()
	n, _ := io.Copy(io.Discard, resp.Body)
	return n, resp.StatusCode == http.StatusOK
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

	// Download: one sustained single-stream read against a large test file —
	// a burst of small requests trips Cloudflare's per-IP rate limiter (429),
	// so Cloudflare is only the fallback, in capped 25MB chunks.
	received, elapsed := timedDownload(ctx, client, "https://fsn1-speed.hetzner.com/10GB.bin")
	if received == 0 {
		downCtx, cancelDown := context.WithTimeout(ctx, phaseDuration)
		for downCtx.Err() == nil {
			n, ok := readOnce(downCtx, client, base+"/__down?bytes=25000000")
			received += n
			if !ok {
				break
			}
		}
		cancelDown()
		elapsed = phaseDuration.Seconds()
	}
	downMbps := 0.0
	if elapsed > 0 {
		downMbps = float64(received) * 8 / elapsed / 1e6
	}

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
	upStart := time.Now()
	upResp, upErr := client.Do(upReq)
	upElapsed := time.Since(upStart).Seconds()
	if upErr == nil {
		io.Copy(io.Discard, upResp.Body)
		upResp.Body.Close()
	}
	upMbps := 0.0
	if upElapsed > 0 && sent.Load() > 0 {
		upMbps = float64(sent.Load()) * 8 / upElapsed / 1e6
	}
	return latency, downMbps, upMbps, nil
}
