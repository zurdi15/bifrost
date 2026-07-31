<script setup lang="ts">
import { computed, onScopeDispose, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { mdiBellOutline, mdiCalendarClock, mdiHarddisk, mdiViewDashboardOutline } from '@mdi/js';

import ConnectionPill from '@/components/ConnectionPill.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import { useLiveStore } from '@/stores/live';
import { formatClock } from '@/utils/format';

const { t } = useI18n();
const live = useLiveStore();

const NAV = [
  { to: '/', key: 'nav.dashboard', icon: mdiViewDashboardOutline, exact: true },
  { to: '/storage', key: 'nav.storage', icon: mdiHarddisk, exact: false },
  { to: '/jobs', key: 'nav.jobs', icon: mdiCalendarClock, exact: false },
  { to: '/settings', key: 'nav.settings', icon: mdiBellOutline, exact: false },
];

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
      <RouterLink to="/" class="wordmark">⌁ bifrost</RouterLink>
      <nav class="nav">
        <RouterLink
          v-for="item in NAV"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :exact-active-class="item.exact ? 'active' : ''"
          :active-class="item.exact ? '' : 'active'"
        >
          {{ t(item.key) }}
        </RouterLink>
      </nav>
      <div class="right">
        <ConnectionPill />
        <span class="clock bf-metric">{{ clock }}</span>
      </div>
    </header>

    <main class="content">
      <slot />
    </main>

    <!-- Mobile: the topbar nav collapses into a floating glass dock. -->
    <nav class="dock" :aria-label="t('nav.dashboard')">
      <RouterLink
        v-for="item in NAV"
        :key="item.to"
        :to="item.to"
        class="dock-link"
        :exact-active-class="item.exact ? 'active' : ''"
        :active-class="item.exact ? '' : 'active'"
      >
        <BfIcon :path="item.icon" :size="19" />
        <span class="dock-label">{{ t(item.key) }}</span>
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
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.9rem 1.5rem;
}
.wordmark {
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: 0.01em;
  text-decoration: none;
  background: var(--bf-aurora);
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.nav {
  display: flex;
  gap: 0.3rem;
  margin-left: 1.5rem;
  margin-right: auto;
}
.nav-link {
  padding: 0.3rem 0.75rem;
  border-radius: var(--bf-radius-ctl);
  font-size: 0.82rem;
  font-weight: 550;
  text-decoration: none;
  color: var(--bf-ink-muted);
  transition:
    color var(--bf-dur-150),
    background-color var(--bf-dur-150);
}
.nav-link:hover {
  color: var(--bf-ink);
  background: var(--bf-surface-raised);
}
.nav-link.active {
  color: var(--bf-brand);
  background: var(--bf-brand-tint);
}
.right {
  display: flex;
  align-items: center;
  gap: 0.9rem;
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
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .nav {
    display: none;
  }
  .content {
    padding: 0.5rem 1rem calc(5.5rem + env(safe-area-inset-bottom));
  }
  .dock {
    position: fixed;
    bottom: calc(0.8rem + env(safe-area-inset-bottom));
    left: 50%;
    transform: translateX(-50%);
    z-index: 20;
    display: flex;
    gap: 0.15rem;
    padding: 0.3rem;
    border: 1px solid var(--bf-line);
    border-radius: var(--bf-radius-pill);
    background: color-mix(in srgb, var(--bf-surface) 72%, transparent);
    -webkit-backdrop-filter: blur(18px) saturate(1.4);
    backdrop-filter: blur(18px) saturate(1.4);
    box-shadow: var(--bf-shadow-lift);
  }
  .dock-link {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.12rem;
    min-width: 4rem;
    padding: 0.4rem 0.6rem;
    border-radius: var(--bf-radius-pill);
    text-decoration: none;
    color: var(--bf-ink-muted);
    transition:
      color var(--bf-dur-150),
      background-color var(--bf-dur-150);
  }
  .dock-link.active {
    color: var(--bf-brand);
    background: var(--bf-brand-tint);
  }
  .dock-label {
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }
}
</style>
