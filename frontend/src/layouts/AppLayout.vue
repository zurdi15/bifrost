<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import {
  mdiBellOutline,
  mdiCalendarClock,
  mdiHarddisk,
  mdiPencilOutline,
  mdiRadar,
  mdiRouterNetwork,
  mdiServer,
  mdiViewDashboardOutline,
} from '@mdi/js';

import ConnectionPill from '@/components/ConnectionPill.vue';
import TopbarWeather from '@/components/TopbarWeather.vue';
import { LOCALES, persistLocale } from '@/i18n';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import { useLayoutStore } from '@/stores/layout';
import { useLiveStore } from '@/stores/live';
import { useUiStore } from '@/stores/ui';
import { formatClock } from '@/utils/format';

const { t, locale } = useI18n({ useScope: 'global' });
const live = useLiveStore();

// en ⇄ es (cycles, so adding a locale later costs nothing here).
function nextLocale(): void {
  const at = LOCALES.indexOf(locale.value as (typeof LOCALES)[number]);
  const next = LOCALES[(at + 1) % LOCALES.length];
  locale.value = next;
  persistLocale(next);
}
const ui = useUiStore();
const route = useRoute();

// Saved drag orders are needed by every view — load once here.
onMounted(() => void useLayoutStore().load());

const NAV = [
  { to: '/', key: 'nav.dashboard', icon: mdiViewDashboardOutline, exact: true },
  { to: '/nodes', key: 'nav.nodes', icon: mdiServer, exact: false },
  { to: '/storage', key: 'nav.storage', icon: mdiHarddisk, exact: false },
  { to: '/jobs', key: 'nav.jobs', icon: mdiCalendarClock, exact: false },
  { to: '/gateway', key: 'nav.gateway', icon: mdiRouterNetwork, exact: false },
  { to: '/network', key: 'nav.tailnet', icon: mdiRadar, exact: false },
  { to: '/settings', key: 'nav.settings', icon: mdiBellOutline, exact: false },
];

// Drives the sliding pill in both navs (items are fixed-width).
const activeIndex = computed(() => {
  const index = NAV.findIndex((item) =>
    item.exact ? route.path === item.to : route.path.startsWith(item.to),
  );
  return index === -1 ? 0 : index;
});

const now = ref(Math.floor(Date.now() / 1000));
const timer = setInterval(() => (now.value = Math.floor(Date.now() / 1000)), 1000);
onScopeDispose(() => clearInterval(timer));

const clock = computed(() => formatClock(now.value));
const hubDown = computed(() => live.connection !== 'live');
</script>

<template>
  <div class="app">
    <!-- The bridge: a single thin line of aurora. Frozen and desaturated when
         the hub connection is lost — the hairline IS the connection indicator. -->
    <div class="hairline" :class="{ frozen: hubDown }" aria-hidden="true" />

    <header class="topbar">
      <RouterLink to="/" class="wordmark" aria-label="bifrost">
        <img class="logo" src="/favicon.svg" alt="bifrost" width="22" height="22" />
      </RouterLink>
      <!-- Same language as the mobile dock: an icon cluster with a pill
           that glides to the active section. -->
      <nav class="nav" :style="{ '--i': activeIndex }">
        <span class="nav-pill" aria-hidden="true" />
        <RouterLink
          v-for="item in NAV"
          :key="item.to"
          :to="item.to"
          class="nav-link bf-tip-bottom"
          :exact-active-class="item.exact ? 'active' : ''"
          :active-class="item.exact ? '' : 'active'"
          :data-bf-tip="t(item.key)"
          :aria-label="t(item.key)"
        >
          <BfIcon :path="item.icon" :size="19" />
        </RouterLink>
      </nav>
      <div class="right">
        <button
          class="lang bf-tip-bl bf-metric"
          type="button"
          :data-bf-tip="t('nav.language')"
          :aria-label="t('nav.language')"
          @click="nextLocale"
        >
          {{ String(locale).toUpperCase() }}
        </button>
        <button
          class="edit-mode bf-tip-bl"
          :class="{ on: ui.editing }"
          type="button"
          :data-bf-tip="t('nav.edit')"
          :aria-label="t('nav.edit')"
          @click="ui.editing = !ui.editing"
        >
          <BfIcon :path="mdiPencilOutline" :size="14" />
        </button>
        <ConnectionPill />
        <span class="clock bf-metric">{{ clock }}</span>
        <TopbarWeather />
      </div>
    </header>

    <main class="content">
      <slot />
    </main>

    <!-- Mobile: the topbar nav collapses into a floating glass dock.
         Icons only; the label lives in aria/title. -->
    <nav
      class="dock"
      :style="{ '--i': activeIndex, '--n': NAV.length }"
      :aria-label="t('nav.dashboard')"
    >
      <span class="dock-pill" aria-hidden="true" />
      <RouterLink
        v-for="item in NAV"
        :key="item.to"
        :to="item.to"
        class="dock-link"
        :exact-active-class="item.exact ? 'active' : ''"
        :active-class="item.exact ? '' : 'active'"
        :aria-label="t(item.key)"
        :title="t(item.key)"
      >
        <BfIcon :path="item.icon" :size="21" />
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.app {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}
.hairline {
  view-transition-name: bf-hairline;
  position: sticky;
  top: 0;
  z-index: 10;
  height: 2px;
  background: var(--bf-aurora);
  background-size: 300% 100%;
  animation: bf-aurora-drift 24s linear infinite;
}
.hairline.frozen {
  animation-play-state: paused;
  filter: saturate(0.15) brightness(0.7);
  transition: filter var(--bf-dur-500);
}
/* Wordmark left, nav dead-center, status right. */
.topbar {
  view-transition-name: bf-topbar;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 0.9rem 1.5rem;
}
.wordmark {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  width: fit-content;
  text-decoration: none;
}
.logo {
  display: block;
}
.nav {
  position: relative;
  display: flex;
  padding: 0.28rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-pill);
  background: color-mix(in srgb, var(--bf-surface) 72%, transparent);
}
.nav-pill {
  position: absolute;
  top: 0.28rem;
  left: 0.28rem;
  width: 3rem;
  height: calc(100% - 0.56rem);
  border-radius: var(--bf-radius-pill);
  background: var(--bf-brand-tint);
  transform: translateX(calc(var(--i) * 3rem));
  transition: transform var(--bf-dur-300) var(--bf-ease-spring);
}
.nav-link {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 2.1rem;
  border-radius: var(--bf-radius-pill);
  text-decoration: none;
  color: var(--bf-ink-muted);
  transition: color var(--bf-dur-150);
}
.nav-link:hover {
  color: var(--bf-ink);
}
.nav-link.active {
  color: var(--bf-brand);
}
.right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.9rem;
}
/* Language toggle: same quiet register as the edit button. */
.lang {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  padding: 0 0.3rem;
  border: 1px solid transparent;
  border-radius: var(--bf-radius-ctl);
  background: transparent;
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--bf-ink-faint);
  opacity: 0.6;
  cursor: pointer;
  transition:
    opacity var(--bf-dur-150),
    color var(--bf-dur-150);
}
.lang:hover {
  opacity: 1;
  color: var(--bf-ink);
}
/* Global edit mode: deliberately quiet until you need it. */
.edit-mode {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--bf-radius-ctl);
  background: transparent;
  color: var(--bf-ink-faint);
  opacity: 0.5;
  cursor: pointer;
  transition:
    opacity var(--bf-dur-150),
    color var(--bf-dur-150),
    border-color var(--bf-dur-150);
}
.edit-mode:hover {
  opacity: 1;
  color: var(--bf-ink);
}
.edit-mode.on {
  opacity: 1;
  color: var(--bf-brand);
  border-color: var(--bf-brand);
  background: var(--bf-brand-tint);
}
.clock {
  font-size: 0.85rem;
  color: var(--bf-ink-secondary);
}
.content {
  flex: 1;
  padding: 0.5rem 1.5rem 2.5rem;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

/* ── mobile: floating glass dock ─────────────────────────────────────────── */
.dock {
  display: none;
}
@media (max-width: 720px) {
  .topbar {
    padding: 0.75rem 1rem;
    grid-template-columns: auto 1fr;
  }
  .nav {
    display: none;
  }
  .content {
    padding: 0.5rem 1rem calc(5.5rem + env(safe-area-inset-bottom));
  }
  .dock {
    /* Own view-transition group: hero morphs crossfade the page root, and
       without a name the dock would visibly repaint on every navigation. */
    view-transition-name: bf-dock;
    /* Items shrink so any count of tabs fits the narrowest phones; the pill
       shares the same vars so its slide always lands on the active icon. */
    --dock-item: min(2.9rem, calc((100vw - 3.5rem) / var(--n, 6)));
    --dock-gap: 0.15rem;
    position: fixed;
    bottom: calc(0.8rem + env(safe-area-inset-bottom));
    left: 50%;
    transform: translateX(-50%);
    z-index: 20;
    display: flex;
    gap: var(--dock-gap);
    padding: 0.3rem;
    border: 1px solid var(--bf-line);
    border-radius: var(--bf-radius-pill);
    background: color-mix(in srgb, var(--bf-surface) 72%, transparent);
    -webkit-backdrop-filter: blur(18px) saturate(1.4);
    backdrop-filter: blur(18px) saturate(1.4);
    box-shadow: var(--bf-shadow-lift);
  }
  .dock-pill {
    position: absolute;
    top: 0.3rem;
    left: 0.3rem;
    width: var(--dock-item);
    height: var(--dock-item);
    border-radius: var(--bf-radius-pill);
    background: var(--bf-brand-tint);
    transform: translateX(calc(var(--i) * (var(--dock-item) + var(--dock-gap))));
    transition: transform var(--bf-dur-300) var(--bf-ease-spring);
  }
  .dock-link {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--dock-item);
    height: var(--dock-item);
    border-radius: var(--bf-radius-pill);
    text-decoration: none;
    color: var(--bf-ink-muted);
    transition: color var(--bf-dur-150);
  }
  .dock-link.active {
    color: var(--bf-brand);
  }
}
</style>
