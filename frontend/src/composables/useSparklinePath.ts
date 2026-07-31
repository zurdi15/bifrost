/** Pure sparkline geometry — testable without a DOM. */

export interface SparklineGeometry {
  /** Stroke path ("M … L …") or '' when under 2 points. */
  line: string;
  /** Closed path for the area fill under the line. */
  area: string;
  /** y of the last point (flatline extension anchor). */
  lastY: number;
}

export function sparklinePath(
  points: number[],
  width: number,
  height: number,
  opts: { min?: number; max?: number; pad?: number } = {},
): SparklineGeometry {
  if (points.length < 2) return { line: '', area: '', lastY: height / 2 };

  const pad = opts.pad ?? 1.5;
  let min = opts.min ?? Math.min(...points);
  let max = opts.max ?? Math.max(...points);
  if (max === min) {
    // Flat series: draw it mid-band rather than dividing by zero.
    max += 1;
    min -= 1;
  }

  const usable = height - pad * 2;
  const stepX = width / (points.length - 1);
  const y = (v: number) => pad + (1 - (v - min) / (max - min)) * usable;

  const coords = points.map((v, i) => [i * stepX, y(v)] as const);
  const line = coords
    .map(([px, py], i) => `${i === 0 ? 'M' : 'L'}${round(px)} ${round(py)}`)
    .join(' ');
  const area = `${line} L${round(width)} ${round(height)} L0 ${round(height)} Z`;

  return { line, area, lastY: coords[coords.length - 1][1] };
}

function round(v: number): number {
  return Math.round(v * 100) / 100;
}
