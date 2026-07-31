<script setup lang="ts">
import { computed, onScopeDispose, ref } from 'vue';

import ConnectionPill from '@/components/ConnectionPill.vue';
import { useLiveStore } from '@/stores/live';
import { formatClock } from '@/utils/format';

const live = useLiveStore();

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
      <div class="right">
        <ConnectionPill />
        <span class="clock bf-metric">{{ clock }}</span>
      </div>
    </header>

    <main class="content">
      <slot />
    </main>
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
</style>
