<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, useId, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { INTERNET_ID, type TailnetDevice, type TailnetEdge } from '@/api/tailnet';
import { desyncMs } from '@/composables/useDesync';
import {
  createSimulation,
  mergeEdges,
  type PairEdge,
  type XY,
} from '@/composables/useTailnetLayout';

const props = defineProps<{
  devices: TailnetDevice[];
  edges: TailnetEdge[];
  internet: boolean;
  selected: string | null;
  query: string;
}>();
const emit = defineEmits<{ select: [id: string | null] }>();

const { t } = useI18n();

const HEX = '11,0 5.5,9.5 -5.5,9.5 -11,0 -5.5,-9.5 5.5,-9.5';
const EXPIRY_SOON_S = 14 * 86400;

const uid = useId();
const now = Math.floor(Date.now() / 1000);

// ── world / simulation ───────────────────────────────────────────────────
const wrap = ref<HTMLElement | null>(null);
const world = ref({ w: 1000, h: 620 });
const view = ref({ x: 0, y: 0, w: 1000, h: 620 });
const sim = createSimulation(world.value.w, world.value.h);
const positions = shallowRef<Map<string, XY>>(new Map());
// Nothing renders until the container is measured: the first painted frame
// is already the settled constellation (entrances play over a still sky).
let measured = false;
// While the entrance animations are still playing, container resizes (the
// page measuring its own viewport offset, late chips wrapping the console)
// re-settle instantly; only later ones (opening the dossier) glide.
let bornAt = 0;
let raf = 0;
let nodeDrag: { id: string; cx: number; cy: number; moved: boolean } | null = null;

function pins(): Record<string, XY> {
  return props.internet ? { [INTERNET_ID]: { x: world.value.w / 2, y: 76 } } : {};
}

function tick(): void {
  raf = 0;
  const hot = sim.step();
  positions.value = sim.positions();
  if (hot || nodeDrag?.moved) raf = requestAnimationFrame(tick);
}
function ensureRunning(): void {
  if (!raf) raf = requestAnimationFrame(tick);
}

// Just enough backdrop to cover the pan/zoom clamps (±25% pan, 1.5× zoom
// out) — oversizing it cost real paint area on phones and flickered.
const meshMargin = computed(() => Math.max(600, Math.max(world.value.w, world.value.h) * 0.8));

const ids = computed(() => {
  const list = props.devices.map((d) => d.id);
  if (props.internet) list.push(INTERNET_ID);
  return list;
});
const links = computed(() => props.edges.map((e) => [e.src, e.dst] as const));
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
    sim.setGraph(ids.value, links.value, pins());
    if (!measured) return; // the first ResizeObserver tick settles and paints
    if (!positions.value.size) sim.settle();
    positions.value = sim.positions();
    ensureRunning();
  },
  { immediate: true },
);

let resizeObserver: ResizeObserver | null = null;
onMounted(() => {
  resizeObserver = new ResizeObserver((entries) => {
    const rect = entries[0].contentRect;
    if (rect.width < 60 || rect.height < 60) return;
    const prev = world.value;
    world.value = { w: rect.width, h: rect.height };
    sim.resize(rect.width, rect.height, pins());
    if (!measured) {
      measured = true;
      bornAt = performance.now();
      view.value = { x: 0, y: 0, w: rect.width, h: rect.height };
      sim.setGraph(ids.value, links.value, pins());
      sim.settle();
    } else {
      const kx = rect.width / prev.w;
      const ky = rect.height / prev.h;
      view.value = {
        x: view.value.x * kx,
        y: view.value.y * ky,
        w: view.value.w * kx,
        h: view.value.h * ky,
      };
      // Early resizes (viewport-offset measure, font reflow) freeze: the
      // scaled equilibrium IS an equilibrium — re-annealing would teleport.
      if (performance.now() - bornAt < 1600) sim.settle(0);
    }
    positions.value = sim.positions();
    ensureRunning();
  });
  if (wrap.value) {
    resizeObserver.observe(wrap.value);
    wrap.value.addEventListener('pointerdown', onCapturedDown, true);
    wrap.value.addEventListener('pointermove', onCapturedMove, true);
    wrap.value.addEventListener('pointerup', onCapturedUp, true);
    wrap.value.addEventListener('pointercancel', onCapturedUp, true);
    // Belt and braces for real phones: some browsers still hand a two-finger
    // gesture to page zoom unless the touch/gesture defaults are refused
    // outright (Safari's proprietary gesture* events included).
    wrap.value.addEventListener('touchmove', onTouchMove, { passive: false });
    wrap.value.addEventListener('gesturestart', preventEvent);
    wrap.value.addEventListener('gesturechange', preventEvent);
  }
});
onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  if (raf) cancelAnimationFrame(raf);
  if (wrap.value) {
    wrap.value.removeEventListener('pointerdown', onCapturedDown, true);
    wrap.value.removeEventListener('pointermove', onCapturedMove, true);
    wrap.value.removeEventListener('pointerup', onCapturedUp, true);
    wrap.value.removeEventListener('pointercancel', onCapturedUp, true);
    wrap.value.removeEventListener('touchmove', onTouchMove);
    wrap.value.removeEventListener('gesturestart', preventEvent);
    wrap.value.removeEventListener('gesturechange', preventEvent);
  }
});

function preventEvent(event: Event): void {
  event.preventDefault();
}
function onTouchMove(event: TouchEvent): void {
  if (event.touches.length > 1) event.preventDefault();
}

// ── graph view-models ────────────────────────────────────────────────────
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

function toneNum(device: TailnetDevice): number {
  if (device.exit_node) return 5;
  if (device.tags.length) return 2;
  if (device.external) return 4;
  return 3;
}

interface NodeVm {
  d: TailnetDevice;
  x: number;
  y: number;
  dim: boolean;
  sel: boolean;
  warn: boolean;
  tone: number;
}

const nodes = computed<NodeVm[]>(() =>
  props.devices.flatMap((d) => {
    const at = positions.value.get(d.id);
    if (!at) return [];
    const dimSelect =
      props.selected !== null && props.selected !== d.id && !neighbors.value.has(d.id);
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
        tone: toneNum(d),
      },
    ];
  }),
);

const internetAt = computed(() => positions.value.get(INTERNET_ID));
const internetDim = computed(
  () => props.selected !== null && !neighbors.value.has(INTERNET_ID),
);

/** Both directions of a pair share the same bow, so flows overlay the base. */
function curve(aId: string, bId: string): string {
  const a = positions.value.get(aId);
  const b = positions.value.get(bId);
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

function pairDim(pair: PairEdge): boolean {
  return props.selected !== null && pair.a !== props.selected && pair.b !== props.selected;
}

// ── pan / zoom ───────────────────────────────────────────────────────────
const svg = ref<SVGSVGElement | null>(null);
const viewBox = computed(() => `${view.value.x} ${view.value.y} ${view.value.w} ${view.value.h}`);

function toSvgPoint(clientX: number, clientY: number): XY {
  const rect = svg.value?.getBoundingClientRect();
  if (!rect || rect.width === 0) return { x: world.value.w / 2, y: world.value.h / 2 };
  return {
    x: view.value.x + ((clientX - rect.left) / rect.width) * view.value.w,
    y: view.value.y + ((clientY - rect.top) / rect.height) * view.value.h,
  };
}

function clampView(x: number, y: number, w: number, h: number): void {
  view.value = {
    x: Math.min(world.value.w * 1.25 - w, Math.max(-world.value.w * 0.25, x)),
    y: Math.min(world.value.h * 1.25 - h, Math.max(-world.value.h * 0.25, y)),
    w,
    h,
  };
}

function onWheel(event: WheelEvent): void {
  const at = toSvgPoint(event.clientX, event.clientY);
  const factor = event.deltaY > 0 ? 1.18 : 1 / 1.18;
  const w = Math.min(world.value.w * 1.5, Math.max(world.value.w / 6, view.value.w * factor));
  const h = (w / world.value.w) * world.value.h;
  const kx = (at.x - view.value.x) / view.value.w;
  const ky = (at.y - view.value.y) / view.value.h;
  clampView(at.x - kx * w, at.y - ky * h, w, h);
}

let panFrom: { x: number; y: number } | null = null;
let panMoved = false;

// ── pinch zoom (touch) ───────────────────────────────────────────────────
// Pointers are tracked in the CAPTURE phase on the wrapper, so a finger
// landing on a node still counts: the second finger cancels any drag and
// the constellation stays glued to both fingertips.
let pinching = false;
const activePointers = new Map<number, { x: number; y: number }>();
let pinchStart: {
  dist: number;
  view: { x: number; y: number; w: number; h: number };
  mid: { x: number; y: number };
} | null = null;

function onCapturedDown(event: PointerEvent): void {
  activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  if (activePointers.size !== 2) return;
  pinching = true;
  panFrom = null;
  panMoved = true; // the click that may follow must not deselect
  if (nodeDrag) {
    sim.release(nodeDrag.id);
    nodeDrag = null;
    ensureRunning();
  }
  const [a, b] = [...activePointers.values()];
  pinchStart = {
    dist: Math.hypot(a.x - b.x, a.y - b.y) || 1,
    view: { ...view.value },
    mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
  };
}
function onCapturedMove(event: PointerEvent): void {
  if (!activePointers.has(event.pointerId)) return;
  activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  if (!pinching || !pinchStart || activePointers.size < 2) return;
  const rect = svg.value?.getBoundingClientRect();
  if (!rect || rect.width === 0) return;
  const [a, b] = [...activePointers.values()];
  const dist = Math.hypot(a.x - b.x, a.y - b.y) || 1;
  const factor = pinchStart.dist / dist;
  const w = Math.min(world.value.w * 1.5, Math.max(world.value.w / 6, pinchStart.view.w * factor));
  const h = (w / world.value.w) * world.value.h;
  // The world point that sat under the starting midpoint follows the
  // current midpoint — pinch and two-finger pan in one gesture.
  const anchor = {
    x:
      pinchStart.view.x +
      ((pinchStart.mid.x - rect.left) / rect.width) * pinchStart.view.w,
    y:
      pinchStart.view.y +
      ((pinchStart.mid.y - rect.top) / rect.height) * pinchStart.view.h,
  };
  const cx = ((a.x + b.x) / 2 - rect.left) / rect.width;
  const cy = ((a.y + b.y) / 2 - rect.top) / rect.height;
  clampView(anchor.x - cx * w, anchor.y - cy * h, w, h);
}
function onCapturedUp(event: PointerEvent): void {
  activePointers.delete(event.pointerId);
  if (pinching && activePointers.size < 2) {
    pinching = false;
    pinchStart = null;
  }
}

function onPointerDown(event: PointerEvent): void {
  if (pinching) return;
  panFrom = { x: event.clientX, y: event.clientY };
  panMoved = false;
}
function onPointerMove(event: PointerEvent): void {
  if (pinching || !panFrom) return;
  const rect = svg.value?.getBoundingClientRect();
  if (!rect || rect.width === 0) return;
  const dx = ((event.clientX - panFrom.x) / rect.width) * view.value.w;
  const dy = ((event.clientY - panFrom.y) / rect.height) * view.value.h;
  if (Math.abs(event.clientX - panFrom.x) + Math.abs(event.clientY - panFrom.y) > 3) {
    panMoved = true;
  }
  panFrom = { x: event.clientX, y: event.clientY };
  clampView(view.value.x - dx, view.value.y - dy, view.value.w, view.value.h);
}
function onPointerUp(): void {
  panFrom = null;
}
function resetView(): void {
  view.value = { x: 0, y: 0, w: world.value.w, h: world.value.h };
}
function onBackgroundClick(): void {
  if (!panMoved) emit('select', null);
}

// ── node dragging (physics) ──────────────────────────────────────────────
function onNodeDown(event: PointerEvent, id: string): void {
  if (pinching) return;
  event.stopPropagation();
  (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
  nodeDrag = { id, cx: event.clientX, cy: event.clientY, moved: false };
}
function onNodeMove(event: PointerEvent, id: string): void {
  if (pinching || !nodeDrag || nodeDrag.id !== id) return;
  if (
    !nodeDrag.moved &&
    Math.abs(event.clientX - nodeDrag.cx) + Math.abs(event.clientY - nodeDrag.cy) < 4
  ) {
    return;
  }
  nodeDrag.moved = true;
  const at = toSvgPoint(event.clientX, event.clientY);
  sim.drag(id, at.x, at.y);
  ensureRunning();
}
function onNodeUp(id: string): void {
  if (!nodeDrag || nodeDrag.id !== id) return;
  const wasDrag = nodeDrag.moved;
  nodeDrag = null;
  if (wasDrag) {
    sim.release(id);
    ensureRunning();
  } else {
    emit('select', props.selected === id ? null : id);
  }
}
function onNodeCancel(id: string): void {
  if (nodeDrag?.id === id) {
    nodeDrag = null;
    sim.release(id);
    ensureRunning();
  }
}
</script>

<template>
  <div ref="wrap" class="map" :class="{ picking: selected !== null }">
    <svg
      ref="svg"
      :viewBox="viewBox"
      preserveAspectRatio="xMidYMid slice"
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
        <pattern :id="`${uid}-dotsA`" width="26" height="26" patternUnits="userSpaceOnUse">
          <circle class="dot-a" cx="1.2" cy="1.2" r="1.2" />
        </pattern>
        <pattern :id="`${uid}-dotsB`" width="74" height="74" patternUnits="userSpaceOnUse">
          <circle class="dot-b" cx="2" cy="2" r="1.7" />
        </pattern>
        <radialGradient
          v-for="toneId in [2, 3, 4, 5]"
          :id="`${uid}-g${toneId}`"
          :key="toneId"
        >
          <stop offset="0%" :style="{ stopColor: `var(--bf-aurora-${toneId})` }" stop-opacity="0.28" />
          <stop offset="100%" :style="{ stopColor: `var(--bf-aurora-${toneId})` }" stop-opacity="0" />
        </radialGradient>
        <radialGradient :id="`${uid}-vig`">
          <stop offset="0%" class="vig-in" />
          <stop offset="100%" class="vig-out" />
        </radialGradient>
        <!-- Repeating diagonal bands (userSpace + repeat): translating the
             host group by exactly one period vector loops seamlessly. -->
        <linearGradient
          :id="`${uid}-waveA`"
          gradientUnits="userSpaceOnUse"
          x1="0"
          y1="0"
          x2="520"
          y2="182"
          spreadMethod="repeat"
        >
          <stop offset="0" class="wave-stop-a edge-stop" />
          <stop offset="0.5" class="wave-stop-a peak-stop" />
          <stop offset="1" class="wave-stop-a edge-stop" />
        </linearGradient>
        <linearGradient
          :id="`${uid}-waveB`"
          gradientUnits="userSpaceOnUse"
          x1="0"
          y1="0"
          x2="-560"
          y2="308"
          spreadMethod="repeat"
        >
          <stop offset="0" class="wave-stop-b edge-stop" />
          <stop offset="0.5" class="wave-stop-b peak-stop" />
          <stop offset="1" class="wave-stop-b edge-stop" />
        </linearGradient>
      </defs>

      <!-- Cyber mesh: two dot lattices in WORLD space (they pan and zoom with
           the constellation), each drifting one pattern period for a seamless
           parallax loop. -->
      <g class="mesh" aria-hidden="true">
        <ellipse
          class="vig"
          :cx="world.w / 2"
          :cy="world.h / 2"
          :rx="world.w * 0.62"
          :ry="world.h * 0.62"
          :fill="`url(#${uid}-vig)`"
        />
        <g class="mesh-a">
          <rect
            :x="-meshMargin"
            :y="-meshMargin"
            :width="world.w + meshMargin * 2"
            :height="world.h + meshMargin * 2"
            :fill="`url(#${uid}-dotsA)`"
          />
        </g>
        <g class="mesh-b">
          <rect
            :x="-meshMargin"
            :y="-meshMargin"
            :width="world.w + meshMargin * 2"
            :height="world.h + meshMargin * 2"
            :fill="`url(#${uid}-dotsB)`"
          />
        </g>
        <!-- Dot waves: soft aurora bands wash across the lattice and light
             the dots up as they pass. -->
        <g class="wave-a">
          <rect
            :x="-meshMargin"
            :y="-meshMargin"
            :width="world.w + meshMargin * 2"
            :height="world.h + meshMargin * 2"
            :fill="`url(#${uid}-waveA)`"
          />
        </g>
        <g class="wave-b">
          <rect
            :x="-meshMargin"
            :y="-meshMargin"
            :width="world.w + meshMargin * 2"
            :height="world.h + meshMargin * 2"
            :fill="`url(#${uid}-waveB)`"
          />
        </g>
      </g>

      <!-- Links: each base line draws itself in (staggered, overlapping);
           the slow shimmer of data motes fades up once the web is drawn. -->
      <g class="edges">
        <path
          v-for="(pair, pi) in pairs"
          :key="`${pair.a}|${pair.b}`"
          class="edge"
          :class="{ dim: pairDim(pair) }"
          :d="curve(pair.a, pair.b)"
          :style="{ '--i': pi }"
          pathLength="1"
        >
          <title>{{ pairTitle(pair) }}</title>
        </path>
      </g>
      <g class="flows-idle" aria-hidden="true">
        <path
          v-for="(pair, pi) in pairs"
          :key="`${pair.a}|${pair.b}`"
          class="edge-flow"
          :class="{ dim: pairDim(pair) }"
          :d="curve(pair.a, pair.b)"
          :style="{ '--fd': `${(pi % 9) * -0.35}s` }"
        />
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
        <g class="enter">
          <circle class="halo" r="34" :fill="`url(#${uid}-g5)`" />
          <circle class="orbit" r="19" />
          <circle class="globe" r="11" />
          <ellipse class="meridian" rx="4.5" ry="11" />
          <line class="equator" x1="-11" y1="0" x2="11" y2="0" />
          <text class="label" y="38">{{ t('tailnet.internet') }}</text>
        </g>
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
        :style="{
          '--tone': `var(--bf-aurora-${node.tone})`,
          '--bf-desync': `-${desyncMs(node.d.id)}ms`,
        }"
        role="button"
        tabindex="0"
        :aria-label="node.d.name"
        @pointerdown="onNodeDown($event, node.d.id)"
        @pointermove="onNodeMove($event, node.d.id)"
        @pointerup="onNodeUp(node.d.id)"
        @pointercancel="onNodeCancel(node.d.id)"
        @click.stop
        @keydown.enter.prevent="emit('select', node.sel ? null : node.d.id)"
        @keydown.space.prevent="emit('select', node.sel ? null : node.d.id)"
      >
        <g class="enter" :style="{ '--i': i }">
          <g class="zoom">
            <circle class="halo" r="30" :fill="`url(#${uid}-g${node.tone})`" />
            <circle v-if="node.d.online" class="pulse" r="11" />
            <circle class="orbit" r="19" />
            <g v-if="node.sel" class="reticle" aria-hidden="true">
              <circle class="ret-spin" r="24" />
              <circle class="ret-counter" r="28" />
              <line x1="-34" y1="0" x2="-26" y2="0" />
              <line x1="26" y1="0" x2="34" y2="0" />
              <line x1="0" y1="-34" x2="0" y2="-26" />
              <line x1="0" y1="26" x2="0" y2="34" />
            </g>
            <circle class="ring" r="14" />
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
      <span><i class="swatch dot t2" />{{ t('tailnet.legendTagged') }}</span>
      <span><i class="swatch dot t5" />{{ t('tailnet.exitNode') }}</span>
      <span><i class="swatch dot t4" />{{ t('tailnet.external') }}</span>
      <span><i class="swatch orbit-sw" />{{ t('tailnet.internet') }}</span>
    </div>
  </div>
</template>

<style scoped>
.map {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-card);
  background: var(--bf-bg-deep);
  height: 100%;
  touch-action: none;
}
svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  touch-action: none;
  cursor: grab;
}
svg:active {
  cursor: grabbing;
}

/* ── cyber mesh ── */
.dot-a {
  fill: color-mix(in srgb, var(--bf-ink-faint) 55%, transparent);
}
.dot-b {
  fill: color-mix(in srgb, var(--bf-aurora-3) 30%, transparent);
}
.mesh-a {
  animation: bf-mesh-drift 64s linear infinite;
  --mesh-dx: 26px;
  --mesh-dy: -26px;
}
.mesh-b {
  animation: bf-mesh-drift 90s linear infinite;
  --mesh-dx: -74px;
  --mesh-dy: 74px;
}
.wave-a {
  animation: bf-mesh-drift 21s linear infinite;
  --mesh-dx: 520px;
  --mesh-dy: 182px;
}
.wave-b {
  animation: bf-mesh-drift 34s linear infinite;
  --mesh-dx: -560px;
  --mesh-dy: 308px;
}
.wave-stop-a {
  stop-color: var(--bf-aurora-2);
}
.wave-stop-b {
  stop-color: var(--bf-aurora-4);
}
.edge-stop {
  stop-opacity: 0;
}
.wave-stop-a.peak-stop {
  stop-opacity: 0.055;
}
.wave-stop-b.peak-stop {
  stop-opacity: 0.045;
}
.vig-in {
  stop-color: var(--bf-aurora-3);
  stop-opacity: 0.06;
}
.vig-out {
  stop-color: var(--bf-aurora-3);
  stop-opacity: 0;
}

/* ── links ── */
/* Draw-in: pathLength=1 dash — safe here because base edges do NOT use
   non-scaling-stroke (that combination is what Chromium mis-dashes).
   Staggered ~18ms per link, capped so a big mesh never drags. */
.edge {
  fill: none;
  stroke: color-mix(in srgb, var(--bf-ink-muted) 34%, transparent);
  stroke-width: 1;
  stroke-dasharray: 1;
  animation: bf-draw var(--bf-dur-500) var(--bf-ease-spring) both;
  animation-delay: calc(200ms + min(var(--i, 0), 40) * 18ms);
  transition: opacity var(--bf-dur-300);
}
/* The mote shimmer waits for the web to finish drawing, then fades up. */
.flows-idle {
  animation: bf-fade-in var(--bf-dur-500) both;
  animation-delay: 1000ms;
}
.edge-flow {
  fill: none;
  stroke: color-mix(in srgb, var(--bf-aurora-3) 60%, transparent);
  stroke-width: 1.4;
  stroke-linecap: round;
  stroke-dasharray: 2 14;
  vector-effect: non-scaling-stroke;
  animation: bf-flow 2.6s linear infinite;
  animation-delay: var(--fd, 0s);
  opacity: 0.55;
  transition: opacity var(--bf-dur-300);
}
.edge.dim,
.edge-flow.dim {
  opacity: 0.06;
}

.flow {
  fill: none;
  stroke-width: 1.7;
  stroke-dasharray: 7 9;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
  animation: bf-flow 1.1s linear infinite;
}
.flow.out {
  stroke: var(--bf-aurora-2);
}
.flow.in {
  stroke: var(--bf-aurora-4);
}

/* ── nodes ── */
.node {
  cursor: pointer;
  outline: none;
  transition: opacity var(--bf-dur-300);
}
.node.dim {
  opacity: 0.14;
}
/* Agile entrance: every node gets its own beat (~56ms), overlapping, with
   a hard budget so a 50-device tailnet still assembles in under a second. */
.node .enter,
.internet .enter {
  animation: bf-pop-in var(--bf-dur-500) var(--bf-ease-bounce) both;
  animation-delay: calc(min(var(--i, 0) * 1.4, 22) * var(--bf-stagger-step));
}
.node .zoom {
  transition: transform var(--bf-dur-150) var(--bf-ease-spring);
}
.node:hover .zoom,
.node:focus-visible .zoom {
  transform: scale(1.1);
}

.halo {
  transform-origin: 0 0;
  animation: bf-breathe 5.4s ease-in-out infinite;
  animation-delay: var(--bf-desync, 0ms);
}
.offline .halo {
  opacity: 0.15;
  animation: none;
}

.pulse {
  fill: none;
  stroke: var(--bf-status-up);
  stroke-width: 1;
  transform-origin: 0 0;
  animation: bf-pulse 2.6s ease-out infinite;
  animation-delay: var(--bf-desync, 0ms);
}

.orbit {
  fill: none;
  stroke: color-mix(in srgb, var(--tone, var(--bf-aurora-3)) 50%, transparent);
  stroke-width: 1;
  stroke-dasharray: 2 9;
  transform-origin: 0 0;
  animation: bf-rotate 30s linear infinite;
  animation-delay: var(--bf-desync, 0ms);
  opacity: 0.55;
  transition: opacity var(--bf-dur-150);
}
.node:hover .orbit,
.node.sel .orbit,
.node:focus-visible .orbit {
  opacity: 1;
}
.offline .orbit {
  opacity: 0.25;
}

.reticle line {
  stroke: var(--tone, var(--bf-aurora-2));
  stroke-width: 1.2;
}
.ret-spin {
  fill: none;
  stroke: var(--tone, var(--bf-aurora-2));
  stroke-width: 1;
  stroke-dasharray: 5 6;
  transform-origin: 0 0;
  animation: bf-rotate 5s linear infinite;
}
.ret-counter {
  fill: none;
  stroke: color-mix(in srgb, var(--tone, var(--bf-aurora-2)) 55%, transparent);
  stroke-width: 1;
  stroke-dasharray: 1 10;
  transform-origin: 0 0;
  animation: bf-rotate 9s linear infinite;
  animation-direction: reverse;
}

.ring {
  fill: none;
  stroke: var(--bf-line-strong);
  stroke-width: 1;
  transition: stroke var(--bf-dur-150);
}
.node:hover .ring,
.node.sel .ring,
.node:focus-visible .ring {
  stroke: var(--tone, var(--bf-aurora-2));
}

.core {
  fill: color-mix(in srgb, var(--bf-surface-raised) 92%, transparent);
  stroke: color-mix(in srgb, var(--tone, var(--bf-aurora-3)) 60%, var(--bf-ink-muted));
  stroke-width: 1.2;
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
  transition: fill var(--bf-dur-150);
}
.node.sel .label,
.node:hover .label {
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
.internet .halo {
  animation-duration: 7s;
}
.internet .orbit {
  fill: none;
  stroke: color-mix(in srgb, var(--bf-aurora-5) 45%, transparent);
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

/* ── HUD chrome ── */
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
  flex-wrap: wrap;
  gap: 0.4rem 0.9rem;
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
.swatch.dot {
  width: 7px;
  height: 7px;
  border-radius: var(--bf-radius-pill);
}
.swatch.dot.t2 {
  background: var(--bf-aurora-2);
}
.swatch.dot.t4 {
  background: var(--bf-aurora-4);
}
.swatch.dot.t5 {
  background: var(--bf-aurora-5);
}
.swatch.orbit-sw {
  width: 9px;
  height: 9px;
  border: 1px dashed var(--bf-ink-muted);
  border-radius: var(--bf-radius-pill);
}

@media (max-width: 720px) {
  .legend {
    display: none;
  }
  /* Full-canvas animations repaint the entire SVG every frame — on phone
     GPUs that reads as whole-screen render flicker. The backdrop and the
     mote shimmer hold still on small screens; nodes keep their life. */
  .mesh-a,
  .mesh-b,
  .wave-a,
  .wave-b,
  .edge-flow {
    animation: none;
  }
}
</style>
