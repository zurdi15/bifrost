const BYTE_UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];

export function formatBytes(bytes: number, decimals = 1): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : decimals)} ${BYTE_UNITS[unit]}`;
}

export function formatBps(bytesPerSecond: number): string {
  return `${formatBytes(bytesPerSecond)}/s`;
}

export function formatUptime(bootTs: number | null | undefined, now = Date.now() / 1000): string {
  if (!bootTs || bootTs <= 0 || bootTs > now) return '—';
  let secs = Math.floor(now - bootTs);
  const days = Math.floor(secs / 86400);
  secs -= days * 86400;
  const hours = Math.floor(secs / 3600);
  secs -= hours * 3600;
  const mins = Math.floor(secs / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

/** Compact "2d 3h" / "3h 20m" / "5m" span for a positive amount of seconds.
 * Language-neutral like formatUptime; callers wrap it in "hace {t}" / "{t} ago". */
export function formatDelta(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  if (seconds < 60) return '<1m';
  return formatUptime(1, seconds + 1);
}

export function formatClock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}
