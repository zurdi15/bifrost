/**
 * Bifrost design tokens — the single source of truth.
 *
 * `npm run build:tokens` renders this into src/styles/tokens.css (generated,
 * never hand-edited). Dark is the default theme on :root; a future light theme
 * redefines variables under `html.bf-light` — never Tailwind `dark:` variants.
 *
 * Concept: "the bridge at night". Near-black blue sky, translucent hairlines,
 * and the aurora as a single thin line of light. The aurora gradient is
 * restricted by guard-tokens to src/lib/ and src/layouts/.
 */

export const palette = {
  // Surfaces (night sky, blue tint)
  '--bf-bg': '#0a0d16',
  '--bf-bg-deep': '#070910',
  '--bf-surface': '#121620',
  '--bf-surface-raised': '#171c29',
  '--bf-surface-sunken': '#0d1019',
  '--bf-overlay': 'rgb(7 9 16 / 0.72)',

  // Hairlines
  '--bf-line': 'rgb(148 163 184 / 0.09)',
  '--bf-line-strong': 'rgb(148 163 184 / 0.18)',
  '--bf-line-hover': 'rgb(148 163 184 / 0.28)',

  // Ink
  '--bf-ink-strong': '#ffffff',
  '--bf-ink': '#e7ebf4',
  '--bf-ink-secondary': 'rgb(231 235 244 / 0.72)',
  '--bf-ink-muted': 'rgb(231 235 244 / 0.50)',
  '--bf-ink-faint': 'rgb(231 235 244 / 0.32)',

  // Aurora (the motif — 5 stops green→pink, never full ROYGBIV)
  '--bf-aurora-1': '#34d399',
  '--bf-aurora-2': '#22d3ee',
  '--bf-aurora-3': '#60a5fa',
  '--bf-aurora-4': '#a78bfa',
  '--bf-aurora-5': '#f472b6',
  '--bf-aurora':
    'linear-gradient(90deg, var(--bf-aurora-1), var(--bf-aurora-2), var(--bf-aurora-3), var(--bf-aurora-4), var(--bf-aurora-5), var(--bf-aurora-1))',

  // Interactive accent — the bridge blue
  '--bf-brand': '#60a5fa',
  '--bf-brand-hover': '#93c5fd',
  '--bf-brand-tint': 'rgb(96 165 250 / 0.12)',

  // Status (≥3:1 on --bf-surface; always paired with icon+text, never color alone)
  '--bf-status-up': '#0ca30c',
  '--bf-status-warn': '#fab219',
  '--bf-status-degraded': '#ec835a',
  '--bf-status-down': '#d03b3b',
  '--bf-status-unknown': 'rgb(231 235 244 / 0.35)',
  '--bf-status-up-tint': 'color-mix(in srgb, #0ca30c 12%, transparent)',
  '--bf-status-warn-tint': 'color-mix(in srgb, #fab219 12%, transparent)',
  '--bf-status-degraded-tint': 'color-mix(in srgb, #ec835a 12%, transparent)',
  '--bf-status-down-tint': 'color-mix(in srgb, #d03b3b 12%, transparent)',

  // Chart series (validated against #121620: CVD-safe, all ≥3:1)
  '--bf-chart-1': '#3987e5',
  '--bf-chart-2': '#d95926',
  '--bf-chart-3': '#199e70',
  '--bf-chart-4': '#c98500',
  '--bf-chart-5': '#d55181',
  '--bf-chart-6': '#008300',
  '--bf-chart-7': '#9085e9',
  '--bf-chart-8': '#e66767',
  '--bf-chart-grid': 'rgb(148 163 184 / 0.08)',

  // Fixed hue → metric mapping (color follows the entity, app-wide)
  '--bf-metric-cpu': 'var(--bf-chart-1)',
  '--bf-metric-mem': 'var(--bf-chart-7)',
  '--bf-metric-net-rx': 'var(--bf-chart-3)',
  '--bf-metric-net-tx': 'var(--bf-chart-2)',
  '--bf-metric-disk': 'var(--bf-chart-4)',
  '--bf-metric-temp': 'var(--bf-chart-8)',
} as const;

export const motion = {
  '--bf-ease-spring': 'cubic-bezier(0.22, 1, 0.36, 1)',
  '--bf-ease-bounce': 'cubic-bezier(0.34, 1.3, 0.5, 1)',
  '--bf-dur-50': '50ms',
  '--bf-dur-150': '150ms',
  '--bf-dur-300': '300ms',
  '--bf-dur-500': '500ms',
  '--bf-dur-800': '800ms',
  '--bf-stagger-step': '40ms',
} as const;

export const shape = {
  '--bf-radius-card': '14px',
  '--bf-radius-ctl': '9px',
  '--bf-radius-pill': '999px',
  '--bf-font-sans': "'Schibsted Grotesk Variable', system-ui, sans-serif",
  '--bf-font-mono': "'JetBrains Mono Variable', ui-monospace, monospace",
  '--bf-shadow-lift': '0 12px 32px -16px rgb(0 0 0 / 0.6)',
  '--bf-shimmer': 'rgb(167 139 250 / 0.06)',
  '--bf-focus': '0 0 0 2px var(--bf-bg), 0 0 0 4px var(--bf-brand)',
} as const;

export const tokens = { ...palette, ...motion, ...shape } as const;

export type TokenName = keyof typeof tokens;

/** Node status → status token suffix, shared by StatusDot/Chip/NodeCard. */
export const statusToken: Record<string, string> = {
  online: 'up',
  degraded: 'degraded',
  offline: 'down',
  pending: 'warn',
  new: 'unknown',
  disabled: 'unknown',
  unknown: 'unknown',
};
