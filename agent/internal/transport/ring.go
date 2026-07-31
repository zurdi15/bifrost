package transport

import "sync"

// Entry is a serialized, sequenced frame awaiting hub acknowledgement.
type Entry struct {
	Seq   uint64
	Frame []byte
}

// Ring buffers un-acked data frames so a reconnect can resume without loss.
// On overflow it thins the oldest half — keeping 1 of every 6 frames — which
// degrades old raw metrics to ~1min resolution instead of dropping them all
// or growing without bound.
type Ring struct {
	mu       sync.Mutex
	entries  []Entry
	capacity int
}

const thinningKeep = 6

func NewRing(capacity int) *Ring {
	if capacity < thinningKeep*2 {
		capacity = thinningKeep * 2
	}
	return &Ring{capacity: capacity}
}

func (r *Ring) Push(seq uint64, frame []byte) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if len(r.entries) >= r.capacity {
		r.thin()
	}
	r.entries = append(r.entries, Entry{Seq: seq, Frame: frame})
}

// thin compacts the oldest half keeping every thinningKeep-th entry.
// Caller holds the lock.
func (r *Ring) thin() {
	half := len(r.entries) / 2
	kept := make([]Entry, 0, len(r.entries)-half+half/thinningKeep+1)
	for i, e := range r.entries[:half] {
		if i%thinningKeep == 0 {
			kept = append(kept, e)
		}
	}
	r.entries = append(kept, r.entries[half:]...)
}

// AckUpTo drops every entry with seq <= upto.
func (r *Ring) AckUpTo(upto uint64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	idx := 0
	for idx < len(r.entries) && r.entries[idx].Seq <= upto {
		idx++
	}
	r.entries = r.entries[idx:]
}

// After returns a copy of every entry with seq > after, oldest first.
func (r *Ring) After(after uint64) []Entry {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]Entry, 0, len(r.entries))
	for _, e := range r.entries {
		if e.Seq > after {
			out = append(out, e)
		}
	}
	return out
}

func (r *Ring) Len() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.entries)
}
