package transport

import (
	"fmt"
	"testing"
)

func TestRingPushAckAfter(t *testing.T) {
	r := NewRing(100)
	for i := 1; i <= 10; i++ {
		r.Push(uint64(i), []byte(fmt.Sprintf("f%d", i)))
	}
	if r.Len() != 10 {
		t.Fatalf("len = %d, want 10", r.Len())
	}

	r.AckUpTo(4)
	if r.Len() != 6 {
		t.Fatalf("after ack len = %d, want 6", r.Len())
	}

	entries := r.After(7)
	if len(entries) != 3 {
		t.Fatalf("After(7) = %d entries, want 3", len(entries))
	}
	if entries[0].Seq != 8 || entries[2].Seq != 10 {
		t.Fatalf("After(7) seqs wrong: %+v", entries)
	}
}

func TestRingOverflowThinsOldestHalf(t *testing.T) {
	r := NewRing(120)
	for i := 1; i <= 121; i++ {
		r.Push(uint64(i), nil)
	}
	// On the 121st push the oldest 60 collapse to every 6th (10 kept),
	// so: 10 + 60 remaining + 1 new = 71.
	if r.Len() != 71 {
		t.Fatalf("len after thinning = %d, want 71", r.Len())
	}
	// Newest entries are always intact.
	entries := r.After(115)
	if len(entries) != 6 {
		t.Fatalf("newest entries lost: got %d, want 6", len(entries))
	}
	// Ordering is preserved.
	all := r.After(0)
	for i := 1; i < len(all); i++ {
		if all[i].Seq <= all[i-1].Seq {
			t.Fatalf("out of order at %d: %d <= %d", i, all[i].Seq, all[i-1].Seq)
		}
	}
}

func TestRingAckEverything(t *testing.T) {
	r := NewRing(50)
	for i := 1; i <= 5; i++ {
		r.Push(uint64(i), nil)
	}
	r.AckUpTo(999)
	if r.Len() != 0 {
		t.Fatalf("len = %d, want 0", r.Len())
	}
}
