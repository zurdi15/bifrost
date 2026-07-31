/** Deterministic per-id animation offset so pulses never beat in unison. */
export function desyncMs(id: string, periodMs = 2400): number {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0;
  }
  return Math.abs(hash) % periodMs;
}
