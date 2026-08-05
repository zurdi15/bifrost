<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { mdiChevronDown, mdiEyeOffOutline } from '@mdi/js';

import BookmarksSection from '@/components/BookmarksSection.vue';
import ContainerCard from '@/components/ContainerCard.vue';
import ExpandingSearch from '@/components/ExpandingSearch.vue';
import ServicesSection from '@/components/ServicesSection.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import { GROUP_MODES, useDashboardStore } from '@/stores/dashboard';
import { useLiveStore } from '@/stores/live';
import { useUiStore } from '@/stores/ui';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

// The active tab lives in the URL (/#bookmarks) so both are deep-linkable.
const tab = computed<'services' | 'bookmarks'>({
  get: () => (route.hash === '#bookmarks' ? 'bookmarks' : 'services'),
  set: (value) =>
    void router.replace({ hash: value === 'bookmarks' ? '#bookmarks' : '' }),
});

// Switching tabs slides the panel in from the side you moved toward
// (bookmarks sits to the right of services, like its tab).
const swap = ref<'left' | 'right'>('right');
watch(tab, (next) => {
  swap.value = next === 'bookmarks' ? 'right' : 'left';
  openPanel.value = null;
});

// The active-tab underline glides on transform only (translate + scale of a
// 1px bar): left/width are not compositor-friendly, so we measure the tab.
const servicesTab = ref<HTMLButtonElement | null>(null);
const bookmarksTab = ref<HTMLButtonElement | null>(null);
const tabsEl = ref<HTMLElement | null>(null);
const ink = ref({ x: 0, w: 0 });
function placeInk(): void {
  const el = (tab.value === 'bookmarks' ? bookmarksTab : servicesTab).value;
  if (el) ink.value = { x: el.offsetLeft, w: el.offsetWidth };
}
watch(tab, placeInk, { flush: 'post' });
// Tabs change width outside our control (font load, the running count) and
// slide sideways while the machines rail animates open/shut (the centered
// row re-centers as .main resizes) — observing the nav itself catches both.
let inkObserver: ResizeObserver | null = null;
onMounted(() => {
  placeInk();
  inkObserver = new ResizeObserver(() => {
    placeInk();
    alignRail();
  });
  for (const el of [servicesTab.value, bookmarksTab.value, tabsEl.value, mainEl.value]) {
    if (el) inkObserver.observe(el);
  }
  document.addEventListener('pointerdown', onDocPointerDown);
});
onBeforeUnmount(() => {
  inkObserver?.disconnect();
  document.removeEventListener('pointerdown', onDocPointerDown);
});

// ── machines rail alignment ──
// The first machine card sits level with the first service card whatever the
// group mode renders above the grid (heading or not): measured via offsetTop
// (transform-free, so entrance animations can't skew it), self-correcting on
// any relayout through the shared ResizeObserver.
const mainEl = ref<HTMLElement | null>(null);
const railStackEl = ref<HTMLElement | null>(null);
const railNudge = ref(16);

function docTop(el: HTMLElement): number {
  let y = 0;
  let cursor: HTMLElement | null = el;
  while (cursor) {
    y += cursor.offsetTop;
    cursor = cursor.offsetParent as HTMLElement | null;
  }
  return y;
}

function alignRail(): void {
  const serviceCard = mainEl.value?.querySelector<HTMLElement>('.grid > *');
  const railCard = railStackEl.value?.firstElementChild as HTMLElement | null;
  if (!serviceCard || !railCard) return;
  const delta = docTop(serviceCard) - docTop(railCard);
  if (Math.abs(delta) < 1) return;
  railNudge.value = Math.max(10, railNudge.value + delta);
}

const ui = useUiStore();
const live = useLiveStore();
const dash = useDashboardStore();
// Machines (node-UI cards) live in their own right-hand rail; every count
// and grid below is services only.
const nodeCards = computed(() => live.containerList.filter((c) => c.source === 'node'));
const gridContainers = computed(() => live.containerList.filter((c) => c.source !== 'node'));
const runningCount = computed(
  () => gridContainers.value.filter((c) => c.state === 'running').length,
);

// ── shared toolbar ──
// It lives up here, outside the tab swap, so the search never remounts when
// changing tabs; group-by/filter-by simply vanish on the bookmarks tab.
const hasServices = computed(
  () => gridContainers.value.length > 0 || live.hiddenContainers.length > 0,
);
const sources = computed(() => {
  const seen = new Map<string, string>();
  for (const container of [...live.containerList, ...live.hiddenContainers]) {
    seen.set(container.node_uuid, container.node_name);
  }
  return [...seen.entries()].map(([uuid, name]) => ({ uuid, name }));
});
const activeFilters = computed(
  () => (dash.nodeFilter ? 1 : 0) + (dash.showHidden ? 1 : 0),
);
const currentModeLabel = computed(
  () => GROUP_MODES.find((mode) => mode.id === dash.groupMode)!.label,
);
const searchPlaceholder = computed(() =>
  tab.value === 'services' ? t('services.searchPlaceholder') : t('bookmarks.searchPlaceholder'),
);

const openPanel = ref<'group' | 'filter' | null>(null);
function togglePanel(panel: 'group' | 'filter'): void {
  openPanel.value = openPanel.value === panel ? null : panel;
}
// Picking a mode is a radio choice — the panel has done its job, close it.
function pickMode(mode: (typeof GROUP_MODES)[number]['id']): void {
  dash.groupMode = mode;
  openPanel.value = null;
}
function toggleNode(uuid: string): void {
  dash.nodeFilter = dash.nodeFilter === uuid ? null : uuid;
}
const toolbarEl = ref<HTMLElement | null>(null);
function onDocPointerDown(event: PointerEvent): void {
  if (openPanel.value && !toolbarEl.value?.contains(event.target as Node)) {
    openPanel.value = null;
  }
}
// No machines → give services the full width.
const showAside = computed(() => nodeCards.value.length > 0);
// The rail belongs to the services tab; bookmarks gets the full width. The
// aside stays mounted so both directions can animate (column glide + slide).
const railHidden = computed(() => tab.value !== 'services');
</script>

<template>
  <!-- The dashboard is what you *use*: services, bookmarks, widgets.
       Infrastructure health lives in its own Nodes section. -->
  <div class="dash" :class="{ 'with-aside': showAside, 'rail-off': railHidden }">
    <!-- Full-bleed row: the tab rule runs edge to edge, across the rail too,
         so it never shifts while the rail column animates open or shut. -->
    <nav
      ref="tabsEl"
      class="tabs"
      role="tablist"
      :style="{ '--ink-x': ink.x, '--ink-w': ink.w }"
    >
        <button
          ref="servicesTab"
          class="tab"
          :class="{ active: tab === 'services' }"
          role="tab"
          :aria-selected="tab === 'services'"
          @click="tab = 'services'"
        >
          {{ t('services.title') }}
          <span v-if="gridContainers.length > 0" class="tab-count bf-metric">
            {{ runningCount }}/{{ gridContainers.length }}
          </span>
        </button>
        <button
          ref="bookmarksTab"
          class="tab"
          :class="{ active: tab === 'bookmarks' }"
          role="tab"
          :aria-selected="tab === 'bookmarks'"
          @click="tab = 'bookmarks'"
        >
          {{ t('bookmarks.title') }}
        </button>
        <span class="tab-ink" aria-hidden="true" />
    </nav>

    <div ref="mainEl" class="main">
      <div ref="toolbarEl" class="toolbar">
        <template v-if="tab === 'services' && hasServices">
          <button
            class="action"
            :class="{ open: openPanel === 'group' }"
            type="button"
            :aria-expanded="openPanel === 'group'"
            @click="togglePanel('group')"
          >
            {{ t('services.groupBy') }}
            <span class="action-hint">{{ t(currentModeLabel) }}</span>
            <BfIcon class="chev" :path="mdiChevronDown" :size="14" />
          </button>
          <button
            class="action"
            :class="{ open: openPanel === 'filter', engaged: activeFilters > 0 }"
            type="button"
            :aria-expanded="openPanel === 'filter'"
            @click="togglePanel('filter')"
          >
            {{ t('services.filterBy') }}
            <span v-if="activeFilters > 0" class="action-count bf-metric">
              {{ activeFilters }}
            </span>
            <BfIcon class="chev" :path="mdiChevronDown" :size="14" />
          </button>
        </template>
        <ExpandingSearch
          v-model="dash.query"
          :placeholder="searchPlaceholder"
          :label="t('services.search')"
        />

        <!-- Floating option panels: anchored here so opening one never
             reflows the content below. Same chip language for both. -->
        <div
          v-if="openPanel === 'group'"
          class="panel"
          role="group"
          :aria-label="t('services.groupBy')"
        >
          <button
            v-for="mode in GROUP_MODES"
            :key="mode.id"
            class="filter"
            :class="{ active: dash.groupMode === mode.id }"
            type="button"
            :aria-pressed="dash.groupMode === mode.id"
            @click="pickMode(mode.id)"
          >
            {{ t(mode.label) }}
          </button>
        </div>
        <div
          v-else-if="openPanel === 'filter'"
          class="panel"
          role="group"
          :aria-label="t('services.filterBy')"
        >
          <button
            v-if="live.hiddenContainers.length > 0"
            class="filter"
            :class="{ active: dash.showHidden }"
            type="button"
            @click="dash.showHidden = !dash.showHidden"
          >
            <BfIcon :path="mdiEyeOffOutline" :size="12" />
            {{ t('service.showHidden', { count: live.hiddenContainers.length }) }}
          </button>
          <button
            v-for="source in sources"
            :key="source.uuid"
            class="filter"
            :class="{ active: dash.nodeFilter === source.uuid }"
            type="button"
            @click="toggleNode(source.uuid)"
          >
            {{ source.name }}
          </button>
        </div>
      </div>

      <div
        :key="tab"
        :class="swap === 'right' ? 'bf-slide-in-right' : 'bf-slide-in-left'"
      >
        <ServicesSection v-if="tab === 'services'" embedded />
        <BookmarksSection v-else embedded />
      </div>
    </div>

    <!-- Machines get their own rail where the ambient widgets used to sit:
         one card wide, stacked, out of the service grids entirely. -->
    <aside
      v-if="showAside"
      class="aside rail"
      :aria-label="t('nav.nodes')"
      :inert="railHidden"
      :style="{ '--rail-nudge': `${railNudge}px` }"
    >
      <div class="rail-body">
        <h2 class="rail-title">{{ t('nav.nodes') }}</h2>
        <div ref="railStackEl" class="rail-stack bf-stagger">
          <ContainerCard
            v-for="(machine, i) in nodeCards"
            :key="`${machine.node_uuid}:${machine.name}`"
            :container="machine"
            :style="{ '--i': i }"
          />
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.tabs {
  grid-column: 1 / -1;
  position: relative;
  display: flex;
  justify-content: center;
  gap: 0.75rem;
  margin: 1rem 0 0.2rem;
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
/* Underline: a 1px bar translated to the active tab and stretched to its
   width — transform-only, so it glides between tabs. */
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
/* ── shared toolbar ── */
.toolbar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.35rem;
  margin: 1rem 0 1.1rem;
}
/* Every toolbar pill is exactly the same height: the row must not budge
   when the services-only buttons vanish on the bookmarks tab. */
.action {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font: inherit;
  font-size: 0.72rem;
  font-weight: 550;
  height: 1.65rem;
  padding: 0 0.4rem 0 0.65rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-pill);
  background: transparent;
  color: var(--bf-ink-muted);
  cursor: pointer;
  transition:
    color var(--bf-dur-150),
    border-color var(--bf-dur-150),
    background-color var(--bf-dur-150);
}
.action:hover {
  border-color: var(--bf-line-hover);
  color: var(--bf-ink);
}
.action.open {
  color: var(--bf-ink);
  background: var(--bf-surface-raised);
}
/* A filter is applied while its panel is closed: keep the button lit. */
.action.engaged {
  color: var(--bf-brand);
  border-color: var(--bf-brand);
  background: var(--bf-brand-tint);
}
.action-hint {
  font-weight: 500;
  color: var(--bf-ink-faint);
}
.action-count {
  font-size: 0.66rem;
  font-weight: 500;
}
.chev {
  transition: transform var(--bf-dur-150);
}
.action.open .chev {
  transform: rotate(180deg);
}
/* Floating option panel: anchored under the toolbar's right edge so opening
   it never reflows the grid below. Drops in; leaves instantly. */
.panel {
  position: absolute;
  top: calc(100% + 0.35rem);
  right: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.35rem;
  max-width: 100%;
  padding: 0.5rem;
  border: 1px solid var(--bf-line-strong);
  border-radius: var(--bf-radius-ctl);
  background: var(--bf-surface-raised);
  box-shadow: var(--bf-shadow-lift);
  animation: dash-drop-in var(--bf-dur-300) var(--bf-ease-spring) both;
}
@keyframes dash-drop-in {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.filter {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font: inherit;
  font-size: 0.72rem;
  padding: 0.15rem 0.6rem;
  border-radius: var(--bf-radius-pill);
  border: 1px solid var(--bf-line);
  background: transparent;
  color: var(--bf-ink-muted);
  cursor: pointer;
  transition:
    color var(--bf-dur-150),
    border-color var(--bf-dur-150),
    background-color var(--bf-dur-150);
}
.filter:hover {
  border-color: var(--bf-line-hover);
  color: var(--bf-ink);
}
.filter.active {
  color: var(--bf-brand);
  border-color: var(--bf-brand);
  background: var(--bf-brand-tint);
}

/* Narrow screens: the expanded search field would shove the group/filter
   pills off the left edge. While it's open the pills yield the row (exits
   are instant by design); closing the search brings them straight back. */
@media (max-width: 720px) {
  .toolbar:has(.search.open) .action {
    display: none;
  }
  .toolbar :deep(.search.open .search-input) {
    width: clamp(11rem, 60vw, 16rem);
  }
}

.dash {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0 2rem;
  align-items: start;
}
@media (min-width: 1100px) {
  .dash.with-aside {
    grid-template-columns: minmax(0, 1fr) 300px;
    /* No width animation: a gliding column re-wrapped the service cards on
       every frame of the glide. The column snaps (one reflow, masked by the
       tab panel's own entrance) and the rail body slides in after it. */
  }
  .dash.with-aside.rail-off {
    grid-template-columns: minmax(0, 1fr) 0px;
    column-gap: 0;
  }
  .dash > .aside {
    position: sticky;
    top: 0.5rem;
    margin-top: 0;
    /* Clips the rigid rail body while its column narrows. */
    overflow: hidden;
  }
  /* Fixed width so cards slide away as a block instead of re-wrapping
     at every frame of the column squeeze. */
  .rail-body {
    width: 300px;
  }
}
/* The column snaps into place; the machines then glide in (2 stagger steps
   late). Hiding is instant, per the entrance-only motion rule. */
.rail-body {
  transition:
    transform var(--bf-dur-500) var(--bf-ease-spring) calc(2 * var(--bf-stagger-step)),
    opacity var(--bf-dur-500) var(--bf-ease-spring) calc(2 * var(--bf-stagger-step));
}
.rail-off .rail-body {
  transform: translateX(26px);
  opacity: 0;
  transition: none;
}
@media (max-width: 1099px) {
  /* Stacked layout has no column to animate — the rail simply yields. */
  .dash.rail-off > .aside {
    display: none;
  }
}
/* NODES sits centered on the toolbar row (same 1.65rem line as the pills
   and the search); the measured --rail-nudge (see alignRail) then drops the
   card stack so the first machine card is level with the first service
   card, whatever the group mode renders above the grid. */
.rail-title {
  display: flex;
  align-items: center;
  height: 1.65rem;
  margin: 1rem 0 0;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--bf-ink-muted);
}
.rail-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 0.6rem;
}
@media (min-width: 1100px) {
  .rail-stack {
    margin-top: var(--rail-nudge, 0.6rem);
  }
}
@media (max-width: 1099px) {
  .rail-title {
    margin-top: 1.4rem;
  }
}
</style>
