<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { mdiRefresh } from '@mdi/js';

import {
  fetchTailnet,
  refreshTailnet,
  type TailnetDevice,
  type TailnetEdge,
  type TailnetState,
} from '@/api/tailnet';
import ExpandingSearch from '@/components/ExpandingSearch.vue';
import TailnetDossier from '@/components/TailnetDossier.vue';
import TailnetMap from '@/components/TailnetMap.vue';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import { useLiveStore } from '@/stores/live';
import { formatClock } from '@/utils/format';

const { t } = useI18n();
const live = useLiveStore();

const state = ref<TailnetState | null>(null);
const loaded = ref(false);
const refreshing = ref(false);
const selected = ref<string | null>(null);
const query = ref('');

async function load(): Promise<void> {
  try {
    state.value = await fetchTailnet();
  } finally {
    loaded.value = true;
  }
}
onMounted(load);
// tailnet.* bus events land here via the live socket — refetch on any.
watch(() => live.tailnetVersion, load);

async function resync(): Promise<void> {
  if (refreshing.value) return;
  refreshing.value = true;
  try {
    state.value = await refreshTailnet();
  } finally {
    refreshing.value = false;
  }
}

// ── fleet view ──
// The bifrost network is always chartable: the hub and every node it knows,
// wired the way they actually connect — agents dial the hub's WebSocket, the
// hub dials endpoint checks. Without a (non-empty) tailnet it is the only
// view; with one, tabs switch between both nets, deep-linked via #fleet.
const HUB_ID = 'bifrost-hub';
const route = useRoute();
const router = useRouter();
const fleetForced = computed(
  () =>
    loaded.value &&
    state.value !== null &&
    (!state.value.configured || state.value.devices.length === 0),
);
const showTabs = computed(() => loaded.value && state.value !== null && !fleetForced.value);
const tab = computed<'tailnet' | 'fleet'>({
  get: () => (route.hash === '#fleet' ? 'fleet' : 'tailnet'),
  set: (value) => void router.replace({ hash: value === 'fleet' ? '#fleet' : '' }),
});
const fleetMode = computed(
  () => fleetForced.value || (showTabs.value && tab.value === 'fleet'),
);
// Different nets, different citizens — a selection never survives the switch.
watch(tab, () => {
  selected.value = null;
});

// Sliding ink underline, same instrument as the dashboard tabs.
const tailnetTab = ref<HTMLButtonElement | null>(null);
const fleetTab = ref<HTMLButtonElement | null>(null);
const tabsEl = ref<HTMLElement | null>(null);
const ink = ref({ x: 0, w: 0 });
function placeInk(): void {
  const el = (tab.value === 'fleet' ? fleetTab : tailnetTab).value;
  if (el) ink.value = { x: el.offsetLeft, w: el.offsetWidth };
}
watch(tab, placeInk, { flush: 'post' });
let inkObserver: ResizeObserver | null = null;
watch(
  showTabs,
  async (visible) => {
    if (!visible) return;
    await nextTick();
    placeInk();
    inkObserver ??= new ResizeObserver(placeInk);
    for (const el of [tailnetTab.value, fleetTab.value, tabsEl.value]) {
      if (el) inkObserver.observe(el);
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => inkObserver?.disconnect());

function fleetDevice(partial: Partial<TailnetDevice> & { id: string; name: string }): TailnetDevice {
  return {
    fqdn: '',
    hostname: partial.name,
    ips: [],
    os: '',
    user: '',
    tags: [],
    online: true,
    last_seen: 0,
    expires: 0,
    key_expiry_disabled: true,
    client_version: '',
    update_available: false,
    authorized: true,
    external: false,
    exit_node: false,
    routes: [],
    blocks_incoming: false,
    ...partial,
  } as TailnetDevice;
}

const fleetDevices = computed<TailnetDevice[]>(() => [
  fleetDevice({
    id: HUB_ID,
    name: 'bifrost',
    tags: ['hub'],
    online: live.connection === 'live',
  }),
  ...live.nodeList.map((node) =>
    fleetDevice({
      id: node.uuid,
      name: node.name,
      hostname: node.name,
      os: node.os ?? '',
      tags: [node.kind],
      online: node.status === 'online',
      last_seen: node.last_seen ?? 0,
      client_version: node.agent_version ?? '',
    }),
  ),
]);
const fleetEdges = computed<TailnetEdge[]>(() =>
  live.nodeList.map((node) =>
    node.kind === 'endpoint'
      ? { src: HUB_ID, dst: node.uuid, ports: ['checks'] }
      : { src: node.uuid, dst: HUB_ID, ports: ['ws'] },
  ),
);

const devices = computed(() =>
  fleetMode.value ? fleetDevices.value : (state.value?.devices ?? []),
);
const edges = computed(() => (fleetMode.value ? fleetEdges.value : (state.value?.edges ?? [])));
const onlineCount = computed(() => devices.value.filter((d) => d.online).length);
const selectedDevice = computed(
  () => devices.value.find((d) => d.id === selected.value) ?? null,
);
const syncClock = computed(() =>
  state.value && state.value.fetched_at > 0 ? formatClock(state.value.fetched_at) : '—',
);
const unresolved = computed(() => state.value?.policy?.unresolved ?? []);

// Desktop fills the viewport: the map takes 100dvh minus everything above it
// (measured, so a wrapping console never miscalculates) and the page itself
// never scrolls — the dossier scrolls its own content instead.
const bodyEl = ref<HTMLElement | null>(null);
const bodyTop = ref(0);
function measure(): void {
  if (bodyEl.value) {
    bodyTop.value = Math.round(bodyEl.value.getBoundingClientRect().top + window.scrollY);
  }
}
const fontsReady = ref(false);
onMounted(() => {
  window.addEventListener('resize', measure);
  // SPA navigation overlaps the entering and leaving views for a beat (the
  // bf-view transition has no out-in mode), so an early measure reads a top
  // pushed down by the leaving page. Re-measure once the swap settles.
  requestAnimationFrame(measure);
  window.setTimeout(measure, 400);
  // The map mounts once web fonts have landed too — their reflow is the last
  // thing that nudges the layout under the constellation.
  void document.fonts.ready.then(() => {
    fontsReady.value = true;
    void nextTick(measure);
  });
});
onBeforeUnmount(() => window.removeEventListener('resize', measure));
watch([loaded, () => state.value?.configured], () => void nextTick(measure), {
  immediate: true,
});
</script>

<template>
  <section>
    <header class="section-head">
      <h2 class="title">{{ t('tailnet.title') }}</h2>
      <span class="head-chips">
        <BfChip v-if="state?.source === 'fixture' && !fleetMode" tone="warn">
          {{ t('tailnet.demo') }}
        </BfChip>
        <BfChip
          v-if="fleetForced"
          tone="unknown"
          class="bf-tip-bottom"
          :data-bf-tip="t('tailnet.fleetTip')"
        >
          {{ t('tailnet.fleetChip') }}
        </BfChip>
        <BfChip v-else-if="!fleetMode && state?.configured && state.tailnet" tone="brand" mono>
          {{ state.tailnet }}
        </BfChip>
      </span>
    </header>

    <!-- Both nets on tap: the tailnet and bifrost's own agent web. -->
    <nav
      v-if="showTabs"
      ref="tabsEl"
      class="tabs"
      role="tablist"
      :style="{ '--ink-x': ink.x, '--ink-w': ink.w }"
    >
      <button
        ref="tailnetTab"
        class="tab"
        :class="{ active: tab === 'tailnet' }"
        role="tab"
        :aria-selected="tab === 'tailnet'"
        @click="tab = 'tailnet'"
      >
        {{ t('tailnet.tabTailnet') }}
        <span class="tab-count bf-metric">{{ state?.devices.length ?? 0 }}</span>
      </button>
      <button
        ref="fleetTab"
        class="tab"
        :class="{ active: tab === 'fleet' }"
        role="tab"
        :aria-selected="tab === 'fleet'"
        @click="tab = 'fleet'"
      >
        {{ t('tailnet.tabFleet') }}
        <span class="tab-count bf-metric">{{ fleetDevices.length }}</span>
      </button>
      <span class="tab-ink" aria-hidden="true" />
    </nav>

    <template v-if="loaded && state">
      <!-- Instrument console: counters, scan filter, re-sync. -->
      <div class="console">
        <span class="readout">
          {{ t('tailnet.hudNodes') }}
          <b class="bf-metric">{{ devices.length }}</b>
        </span>
        <span class="readout">
          {{ t('tailnet.hudOnline') }}
          <b class="bf-metric up">{{ onlineCount }}</b>
        </span>
        <span class="readout">
          {{ t('tailnet.hudLinks') }}
          <b class="bf-metric">{{ edges.length }}</b>
        </span>
        <template v-if="!fleetMode">
          <span class="readout">
            {{ t('tailnet.hudRules') }}
            <b class="bf-metric">{{ state.policy?.rules ?? 0 }}</b>
          </span>
          <span class="readout">
            {{ t('tailnet.hudSync') }}
            <b class="bf-metric">{{ syncClock }}</b>
          </span>
          <BfChip
            v-if="state.error"
            tone="down"
            class="bf-tip-bottom"
            :data-bf-tip="state.error"
          >
            {{ t('tailnet.stale') }}
          </BfChip>
          <BfChip
            v-else-if="unresolved.length"
            tone="warn"
            class="bf-tip-bottom"
            :data-bf-tip="t('tailnet.partialTip', { list: unresolved.join(', ') })"
          >
            {{ t('tailnet.partial') }}
          </BfChip>
        </template>
        <span class="spacer" />
        <ExpandingSearch
          v-model="query"
          :placeholder="t('tailnet.searchPlaceholder')"
          :label="t('tailnet.search')"
        />
        <button
          v-if="!fleetMode"
          class="resync"
          type="button"
          :disabled="refreshing"
          :aria-label="t('tailnet.resync')"
          @click="resync"
        >
          <BfIcon :path="mdiRefresh" :size="14" :class="{ spin: refreshing }" />
          {{ t('tailnet.resync') }}
        </button>
      </div>

      <p v-if="loaded && devices.length === 0" class="empty">{{ t('tailnet.empty') }}</p>

      <div v-else ref="bodyEl" class="body" :style="{ '--body-top': `${bodyTop}px` }">
        <!-- Mount only after the viewport offset is measured: the map's first
             layout is final, so entrances play over a still constellation. -->
        <TailnetMap
          v-if="bodyTop > 0 && fontsReady"
          :devices="devices"
          :edges="edges"
          :internet="!fleetMode && state.internet"
          :selected="selected"
          :query="query"
          @select="selected = $event"
        />
        <TailnetDossier
          v-if="selectedDevice"
          :key="selectedDevice.id"
          :device="selectedDevice"
          :devices="devices"
          :edges="edges"
          @close="selected = null"
          @select="selected = $event"
        />
      </div>
    </template>
  </section>
</template>

<style scoped>
.section-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0 1.1rem;
  flex-wrap: wrap;
}
.title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--bf-ink-secondary);
}
.head-chips {
  display: flex;
  gap: 0.4rem;
  margin-left: auto;
  flex-wrap: wrap;
}

.tabs {
  position: relative;
  display: flex;
  justify-content: center;
  gap: 0.75rem;
  margin: 0 0 0.8rem;
  border-bottom: 1px solid var(--bf-line);
}
.tab {
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 0.35rem 0.85rem 0.55rem;
  border: none;
  background: transparent;
  color: var(--bf-ink-muted);
  cursor: pointer;
  transition: color var(--bf-dur-150);
}
.tab:hover {
  color: var(--bf-ink);
}
.tab.active {
  color: var(--bf-brand);
}
.tab-ink {
  position: absolute;
  bottom: -1px;
  left: 0;
  width: 1px;
  height: 2px;
  background: var(--bf-brand);
  transform: translateX(calc(var(--ink-x) * 1px)) scaleX(var(--ink-w));
  transform-origin: 0 50%;
  transition: transform var(--bf-dur-300) var(--bf-ease-spring);
}
.tab-count {
  font-size: 0.66rem;
  font-weight: 500;
  color: var(--bf-ink-muted);
  margin-left: 0.15rem;
}
.tab.active .tab-count {
  color: var(--bf-brand);
  opacity: 0.75;
}
.empty {
  color: var(--bf-ink-muted);
  padding: 1.6rem 0;
  text-align: center;
}

.console {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.55rem 0.9rem;
  margin-bottom: 0.8rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-card);
  background: color-mix(in srgb, var(--bf-surface) 72%, transparent);
}
.readout {
  display: inline-flex;
  align-items: baseline;
  gap: 0.4rem;
  font-family: var(--bf-font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--bf-ink-faint);
  white-space: nowrap;
}
.readout b {
  font-size: 0.82rem;
  font-weight: 650;
  color: var(--bf-ink);
}
.readout b.up {
  color: var(--bf-status-up);
}
.spacer {
  flex: 1;
}
.resync {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.28rem 0.7rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-pill);
  background: transparent;
  color: var(--bf-ink-secondary);
  font-family: var(--bf-font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  cursor: pointer;
  transition:
    color var(--bf-dur-150),
    border-color var(--bf-dur-150);
}
.resync:hover:not(:disabled) {
  color: var(--bf-ink);
  border-color: var(--bf-line-hover);
}
.resync:disabled {
  opacity: 0.6;
  cursor: default;
}
.resync :deep(.spin) {
  animation: bf-rotate 1s linear infinite;
}

/* One full-bleed stage: the map owns the whole box and the dossier floats
   over it — selecting a node never resizes the map or reflows the sky.
   Height fills the viewport to a slim margin with no page scroll (the
   negative margin swallows the app content's bottom padding below us). */
.body {
  position: relative;
  /* Contain repaints: map + floating dossier composite as one island. */
  isolation: isolate;
  height: calc(100dvh - var(--body-top, 0px) - 1rem);
  margin-bottom: -1.5rem;
  min-height: 20rem;
}
@media (max-width: 720px) {
  /* The floating dock reserves the bottom on mobile — stop just above it. */
  .body {
    height: calc(100dvh - var(--body-top, 0px) - 4.8rem - env(safe-area-inset-bottom, 0px));
    margin-bottom: -0.7rem;
  }
}

/* The dossier is a glass panel pinned over the map's right edge; on small
   screens it becomes a bottom sheet rising over the constellation. */
.body .dossier {
  position: absolute;
  top: 0.9rem;
  right: 0.9rem;
  width: 21rem;
  max-width: calc(100% - 1.8rem);
  max-height: calc(100% - 1.8rem);
  z-index: 5;
}
@media (max-width: 720px) {
  .body .dossier {
    top: auto;
    left: 0.6rem;
    right: 0.6rem;
    bottom: 0.6rem;
    width: auto;
    max-width: none;
    max-height: 62%;
    animation-name: bf-rise-in;
  }
}

</style>
