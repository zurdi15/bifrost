<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { INTERNET_ID, type TailnetDevice, type TailnetEdge } from '@/api/tailnet';
import { desyncMs } from '@/composables/useDesync';
import { computeLayout, mergeEdges, type PairEdge, type XY } from '@/composables/useTailnetLayout';

const props = defineProps<{
  devices: TailnetDevice[];
  edges: TailnetEdge[];
  internet: boolean;
  selected: string | null;
  query: string;
}>();
const emit = defineEmits<{ select: [id: string | null] }>();

const { t } = useI18n();

// Fixed drawing space; the SVG scales to its container.
const W = 1000;
const H = 620;
const HEX = '11,0 5.5,9.5 -5.5,9.5 -11,0 -5.5,-9.5 5.5,-9.5';
const EXPIRY_SOON_S = 14 * 86400;

const glowId = useId();
const now = Math.floor(Date.now() / 1000);

const ids = computed(() => {
  const list = props.devices.map((d) => d.id);
  if (props.internet) list.push(INTERNET_ID);
  return list;
});
const links = computed(() => props.edges.map((e) => [e.src, e.dst] as const));

// Re-run the simulation only when the topology itself changes — a refetch
// with identical devices must not make the constellation jump.
const layout = ref<Map<string, XY>>(new Map());
const fingerprint = computed(
  () =>
    [...ids.value].sort().join() +
    '§' +
    links.value
      .map((l) => `${l[0]}>${l[1]}`)
      .sort()
      .join(),
);
watch(
  fingerprint,
  () => {
    layout.value = computeLayout(
      ids.value,
      links.value,
      W,
      H,
      props.internet ? { [INTERNET_ID]: { x: W / 2, y: 64 } } : {},
    );
  },
  { immediate: true },
);

const byId = computed(() => new Map(props.devices.map((d) => [d.id, d])));
const pairs = computed(() => mergeEdges(props.edges));
const active = computed(() =>
  props.selected
    ? props.edges.filter((e) => e.src === props.selected || e.dst === props.selected)
    : [],
);
const neighbors = computed(() => {
  const set = new Set<string>();
  for (const edge of active.value) {
    set.add(edge.src);
    set.add(edge.dst);
  }
  return set;
});

function matchesQuery(device: TailnetDevice): boolean {
  const q = props.query.trim().toLowerCase();
  if (!q) return true;
  return (
    device.name.toLowerCase().includes(q) ||
    device.user.toLowerCase().includes(q) ||
    device.os.toLowerCase().includes(q) ||
    device.tags.some((tag) => tag.toLowerCase().includes(q)) ||
    device.ips.some((ip) => ip.includes(q))
  );
}

interface NodeVm {
  d: TailnetDevice;
  x: number;
  y: number;
  dim: boolean;
  sel: boolean;
  warn: boolean;
}

const nodes = computed<NodeVm[]>(() =>
  props.devices.flatMap((d) => {
    const at = layout.value.get(d.id);
    if (!at) return [];
    const dimSelect = props.selected !== null && props.selected !== d.id && !neighbors.value.has(d.id);
    return [
      {
        d,
        x: at.x,
        y: at.y,
        dim: dimSelect || !matchesQuery(d),
        sel: props.selected === d.id,
        warn:
          d.update_available ||
          (d.expires > 0 && !d.key_expiry_disabled && d.expires - now < EXPIRY_SOON_S),
      },
    ];
  }),
);

const internetAt = computed(() => layout.value.get(INTERNET_ID));
const internetDim = computed(
  () => props.selected !== null && !neighbors.value.has(INTERNET_ID),
);

/** Both directions of a pair share the same bow, so flows overlay the base. */
function curve(aId: string, bId: string): string {
  const a = layout.value.get(aId);
  const b = layout.value.get(bId);
  if (!a || !b) return '';
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const bow = 0.09 * (aId < bId ? 1 : -1);
  const cx = mx - (b.y - a.y) * bow;
  const cy = my + (b.x - a.x) * bow;
  return `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
}

function endpointName(id: string): string {
  return id === INTERNET_ID ? t('tailnet.internet') : (byId.value.get(id)?.name ?? id);
}

function pairTitle(pair: PairEdge): string {
  const parts: string[] = [];
  if (pair.ab) parts.push(`${endpointName(pair.a)} → ${endpointName(pair.b)} · ${pair.ab.join(', ')}`);
  if (pair.ba) parts.push(`${endpointName(pair.b)} → ${endpointName(pair.a)} · ${pair.ba.join(', ')}`);
  return parts.join('\n');
}

// ── pan / zoom ───────────────────────────────────────────────────────────
const svg = ref<SVGSVGElement | null>(null);
const view = ref({ x: 0, y: 0, w: W, h: H });
const viewBox = computed(() => `${view.value.x} ${view.value.y} ${view.value.w} ${view.value.h}`);

function toSvgPoint(clientX: number, clientY: number): XY {
  const rect = svg.value?.getBoundingClientRect();
  if (!rect || rect.width === 0) return { x: W / 2, y: H / 2 };
  return {
    x: view.value.x + ((clientX - rect.left) / rect.width) * view.value.w,
    y: view.value.y + ((clientY - rect.top) / rect.height) * view.value.h,
  };
}

function clampView(x: number, y: number, w: number, h: number): void {
  view.value = {
    x: Math.min(W * 1.25 - w, Math.max(-W * 0.25, x)),
    y: Math.min(H * 1.25 - h, Math.max(-H * 0.25, y)),
    w,
    h,
  };
}

function onWheel(event: WheelEvent): void {
  const at = toSvgPoint(event.clientX, event.clientY);
  const factor = event.deltaY > 0 ? 1.18 : 1 / 1.18;
  const w = Math.min(W * 1.5, Math.max(W / 6, view.value.w * factor));
  const h = (w / W) * H;
  const kx = (at.x - view.value.x) / view.value.w;
  const ky = (at.y - view.value.y) / view.value.h;
  clampView(at.x - kx * w, at.y - ky * h, w, h);
}

let dragFrom: { x: number; y: number } | null = null;
let dragMoved = false;

function onPointerDown(event: PointerEvent): void {
  dragFrom = { x: event.clientX, y: event.clientY };
  dragMoved = false;
}

function onPointerMove(event: PointerEvent): void {
  if (!dragFrom) return;
  const rect = svg.value?.getBoundingClientRect();
  if (!rect || rect.width === 0) return;
  const dx = ((event.clientX - dragFrom.x) / rect.width) * view.value.w;
  const dy = ((event.clientY - dragFrom.y) / rect.height) * view.value.h;
  if (Math.abs(event.clientX - dragFrom.x) + Math.abs(event.clientY - dragFrom.y) > 3) {
    dragMoved = true;
  }
  dragFrom = { x: event.clientX, y: event.clientY };
  clampView(view.value.x - dx, view.value.y - dy, view.value.w, view.value.h);
}

function onPointerUp(): void {
  dragFrom = null;
}

function resetView(): void {
  view.value = { x: 0, y: 0, w: W, h: H };
}

function onBackgroundClick(): void {
  if (!dragMoved) emit('select', null);
}

function pick(id: string): void {
  if (dragMoved) return;
  emit('select', props.selected === id ? null : id);
}
</script>

<template>
  <div class="map" :class="{ picking: selected !== null }">
    <!-- Radar sweep: pure CSS, sits under the SVG. -->
    <div class="sweep" aria-hidden="true" />
    <svg
      ref="svg"
      :viewBox="viewBox"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      :aria-label="t('tailnet.mapLabel')"
      @wheel.prevent="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointerleave="onPointerUp"
      @click="onBackgroundClick"
      @dblclick="resetView"
    >
      <defs>
        <radialGradient :id="glowId">
          <stop offset="0%" class="glow-in" />
          <stop offset="100%" class="glow-out" />
        </radialGradient>
      </defs>

      <!-- Polar grid: quiet instrument backdrop. -->
      <g class="polar" aria-hidden="true">
        <circle v-for="r in [95, 175, 255]" :key="r" :cx="W / 2" :cy="H / 2" :r="r" />
        <line :x1="W / 2" :y1="H / 2 - 268" :x2="W / 2" :y2="H / 2 + 268" />
        <line :x1="W / 2 - 268" :y1="H / 2" :x2="W / 2 + 268" :y2="H / 2" />
      </g>

      <!-- Base links: every allowed pair, drawn in on load. -->
      <g class="edges">
        <path
          v-for="pair in pairs"
          :key="`${pair.a}|${pair.b}`"
          class="edge"
          :class="{ dim: selected !== null && pair.a !== selected && pair.b !== selected }"
          :d="curve(pair.a, pair.b)"
          pathLength="1"
        >
          <title>{{ pairTitle(pair) }}</title>
        </path>
      </g>

      <!-- Focus flows: directed, cyan out of the selected node, violet in. -->
      <g v-if="selected" class="flows" aria-hidden="true">
        <path
          v-for="edge in active"
          :key="`${edge.src}>${edge.dst}`"
          class="flow"
          :class="edge.src === selected ? 'out' : 'in'"
          :d="curve(edge.src, edge.dst)"
        />
      </g>

      <!-- The outside world, reachable through exit nodes. -->
      <g
        v-if="internet && internetAt"
        class="internet"
        :class="{ dim: internetDim }"
        :transform="`translate(${internetAt.x} ${internetAt.y})`"
        aria-hidden="true"
      >
        <circle class="orbit" r="19" />
        <circle class="globe" r="11" />
        <ellipse class="meridian" rx="4.5" ry="11" />
        <line class="equator" x1="-11" y1="0" x2="11" y2="0" />
        <text class="label" y="38">{{ t('tailnet.internet') }}</text>
      </g>

      <!-- Devices. Nested groups keep translate (attr), entrance (CSS) and
           hover scale (CSS) on separate transforms. -->
      <g
        v-for="(node, i) in nodes"
        :key="node.d.id"
        class="node"
        :class="{
          dim: node.dim,
          sel: node.sel,
          offline: !node.d.online,
          external: node.d.external,
        }"
        :transform="`translate(${node.x} ${node.y})`"
        role="button"
        tabindex="0"
        :aria-label="node.d.name"
        @click.stop="pick(node.d.id)"
        @keydown.enter.prevent="emit('select', node.sel ? null : node.d.id)"
        @keydown.space.prevent="emit('select', node.sel ? null : node.d.id)"
      >
        <g class="enter" :style="{ '--i': i }">
          <g class="zoom" :style="{ '--bf-desync': `-${desyncMs(node.d.id)}ms` }">
            <circle class="halo" r="27" :fill="`url(#${glowId})`" />
            <circle v-if="node.d.online" class="pulse" r="11" />
            <circle class="ring" r="15" />
            <circle v-if="node.d.exit_node" class="exit-ring" r="20" />
            <polygon v-if="node.d.tags.length" class="core" :points="HEX" />
            <circle v-else class="core" r="9.5" />
            <circle class="led" r="2.6" />
            <circle v-if="node.warn" class="warn" cx="11" cy="-11" r="3.2" />
            <text class="label" y="32">{{ node.d.name }}</text>
            <text class="sub bf-metric" y="43">{{ node.d.ips[0] }}</text>
          </g>
        </g>
      </g>
    </svg>

    <!-- HUD frame corners. -->
    <i class="corner tl" aria-hidden="true" /><i class="corner tr" aria-hidden="true" />
    <i class="corner bl" aria-hidden="true" /><i class="corner br" aria-hidden="true" />

    <div class="legend" aria-hidden="true">
      <span><i class="swatch line-out" />{{ t('tailnet.legendOut') }}</span>
      <span><i class="swatch line-in" />{{ t('tailnet.legendIn') }}</span>
      <span><i class="swatch shape-hex" />{{ t('tailnet.legendTagged') }}</span>
      <span><i class="swatch shape-orbit" />{{ t('tailnet.internet') }}</span>
    </div>
  </div>
</template>

<style scoped>
.map {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-card);
  background:
    radial-gradient(
      ellipse at 50% 42%,
      color-mix(in srgb, var(--bf-aurora-3) 5%, transparent),
      transparent 62%
    ),
    var(--bf-bg-deep);
}
svg {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 1000 / 620;
  touch-action: none;
  cursor: grab;
}
svg:active {
  cursor: grabbing;
}

.sweep {
  position: absolute;
  inset: 0;
  margin: auto;
  width: min(140%, 56rem);
  aspect-ratio: 1;
  border-radius: var(--bf-radius-pill);
  background: conic-gradient(
    from 0deg,
    transparent 0deg,
    transparent 300deg,
    color-mix(in srgb, var(--bf-aurora-2) 6%, transparent) 345deg,
    color-mix(in srgb, var(--bf-aurora-2) 14%, transparent) 359deg,
    transparent 360deg
  );
  mask-image: radial-gradient(circle, var(--bf-ink-strong) 30%, transparent 72%);
  animation: bf-rotate 18s linear infinite;
  pointer-events: none;
}

.polar circle,
.polar line {
  fill: none;
  stroke: var(--bf-line);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.polar line {
  stroke-dasharray: 1 7;
}

.edge {
  fill: none;
  stroke: var(--bf-line-strong);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
  stroke-dasharray: 1;
  animation: bf-draw var(--bf-dur-800) var(--bf-ease-spring) both;
  transition: opacity var(--bf-dur-300);
}
.edge.dim {
  opacity: 0.14;
}
.picking .edge:not(.dim) {
  stroke: color-mix(in srgb, var(--bf-ink-muted) 55%, transparent);
}

.flow {
  fill: none;
  stroke-width: 1.6;
  stroke-dasharray: 7 9;
  vector-effect: non-scaling-stroke;
  animation: bf-flow 1.2s linear infinite;
}
.flow.out {
  stroke: var(--bf-aurora-2);
}
.flow.in {
  stroke: var(--bf-aurora-4);
}

.node {
  cursor: pointer;
  outline: none;
  transition: opacity var(--bf-dur-300);
}
.node.dim {
  opacity: 0.15;
}
.node .enter {
  animation: bf-pop-in var(--bf-dur-500) var(--bf-ease-bounce) both;
  animation-delay: calc(min(var(--i, 0), 8) * var(--bf-stagger-step));
}
.node .zoom {
  transition: transform var(--bf-dur-150) var(--bf-ease-spring);
}
.node:hover .zoom,
.node:focus-visible .zoom {
  transform: scale(1.12);
}
.node:focus-visible .ring {
  stroke: var(--bf-brand);
}

.glow-in {
  stop-color: var(--bf-aurora-3);
  stop-opacity: 0.22;
}
.glow-out {
  stop-color: var(--bf-aurora-3);
  stop-opacity: 0;
}
.offline .halo {
  opacity: 0.25;
}

.pulse {
  fill: none;
  stroke: var(--bf-status-up);
  stroke-width: 1;
  transform-origin: 0 0;
  animation: bf-pulse 2.6s ease-out infinite;
  animation-delay: var(--bf-desync, 0ms);
}

.ring {
  fill: none;
  stroke: var(--bf-line-strong);
  stroke-width: 1;
  transition: stroke var(--bf-dur-150);
}
.node.sel .ring {
  stroke: var(--bf-aurora-2);
  stroke-dasharray: 4 5;
  transform-origin: 0 0;
  animation: bf-rotate 14s linear infinite;
}
.exit-ring {
  fill: none;
  stroke: var(--bf-aurora-5);
  stroke-width: 1;
  stroke-dasharray: 2 8;
  opacity: 0.8;
}

.core {
  fill: color-mix(in srgb, var(--bf-surface-raised) 92%, transparent);
  stroke: var(--bf-ink-muted);
  stroke-width: 1.2;
}
.node.sel .core {
  stroke: var(--bf-aurora-2);
}
.node.external .core {
  stroke-dasharray: 3 3;
}
.offline .core {
  stroke: var(--bf-ink-faint);
}

.led {
  fill: var(--bf-status-up);
}
.offline .led {
  fill: var(--bf-status-unknown);
}
.warn {
  fill: var(--bf-status-warn);
  stroke: var(--bf-bg-deep);
  stroke-width: 1;
}

.label {
  font-family: var(--bf-font-mono);
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  text-anchor: middle;
  fill: var(--bf-ink-secondary);
  paint-order: stroke;
  stroke: var(--bf-bg-deep);
  stroke-width: 3px;
}
.node.sel .label {
  fill: var(--bf-ink-strong);
}
.sub {
  font-size: 8.5px;
  text-anchor: middle;
  fill: var(--bf-ink-muted);
  opacity: 0;
  transition: opacity var(--bf-dur-150);
}
.node:hover .sub,
.node.sel .sub,
.node:focus-visible .sub {
  opacity: 1;
}

.internet {
  transition: opacity var(--bf-dur-300);
}
.internet.dim {
  opacity: 0.15;
}
.internet .orbit {
  fill: none;
  stroke: var(--bf-ink-faint);
  stroke-width: 1;
  stroke-dasharray: 3 6;
  transform-origin: 0 0;
  animation: bf-rotate 40s linear infinite;
}
.internet .globe,
.internet .meridian {
  fill: none;
  stroke: var(--bf-ink-muted);
  stroke-width: 1;
}
.internet .equator {
  stroke: var(--bf-ink-muted);
  stroke-width: 1;
}
.internet .label {
  fill: var(--bf-ink-faint);
}

.corner {
  position: absolute;
  width: 14px;
  height: 14px;
  border: 1px solid var(--bf-line-hover);
  pointer-events: none;
}
.corner.tl {
  top: 8px;
  left: 8px;
  border-right: none;
  border-bottom: none;
}
.corner.tr {
  top: 8px;
  right: 8px;
  border-left: none;
  border-bottom: none;
}
.corner.bl {
  bottom: 8px;
  left: 8px;
  border-right: none;
  border-top: none;
}
.corner.br {
  bottom: 8px;
  right: 8px;
  border-left: none;
  border-top: none;
}

.legend {
  position: absolute;
  left: 0.9rem;
  bottom: 0.7rem;
  display: flex;
  gap: 0.9rem;
  font-family: var(--bf-font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--bf-ink-faint);
  pointer-events: none;
}
.legend span {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}
.swatch {
  display: inline-block;
}
.swatch.line-out {
  width: 14px;
  height: 0;
  border-top: 2px dashed var(--bf-aurora-2);
}
.swatch.line-in {
  width: 14px;
  height: 0;
  border-top: 2px dashed var(--bf-aurora-4);
}
.swatch.shape-hex {
  width: 9px;
  height: 9px;
  border: 1px solid var(--bf-ink-muted);
  rotate: 45deg;
}
.swatch.shape-orbit {
  width: 9px;
  height: 9px;
  border: 1px dashed var(--bf-ink-muted);
  border-radius: var(--bf-radius-pill);
}

@media (max-width: 720px) {
  .legend {
    display: none;
  }
}
</style>
