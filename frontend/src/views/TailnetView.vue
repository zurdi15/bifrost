<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { mdiMagnify, mdiRefresh } from '@mdi/js';

import { fetchTailnet, refreshTailnet, type TailnetState } from '@/api/tailnet';
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

const devices = computed(() => state.value?.devices ?? []);
const edges = computed(() => state.value?.edges ?? []);
const onlineCount = computed(() => devices.value.filter((d) => d.online).length);
const selectedDevice = computed(
  () => devices.value.find((d) => d.id === selected.value) ?? null,
);
const syncClock = computed(() =>
  state.value && state.value.fetched_at > 0 ? formatClock(state.value.fetched_at) : '—',
);
const unresolved = computed(() => state.value?.policy?.unresolved ?? []);
</script>

<template>
  <section>
    <header class="section-head">
      <h2 class="title">{{ t('tailnet.title') }}</h2>
      <span class="head-chips">
        <BfChip v-if="state?.source === 'fixture'" tone="warn">{{ t('tailnet.demo') }}</BfChip>
        <BfChip v-if="state?.configured && state.tailnet" tone="brand" mono>
          {{ state.tailnet }}
        </BfChip>
      </span>
    </header>

    <!-- No credentials: the section idles, antenna out. -->
    <div v-if="loaded && state && !state.configured" class="no-uplink">
      <span class="dish" aria-hidden="true" />
      <p class="no-uplink-title">{{ t('tailnet.notConfigured') }}</p>
      <i18n-t keypath="tailnet.notConfiguredBody" tag="p" class="no-uplink-body">
        <template #key>
          <code class="bf-metric">BIFROST_TAILSCALE_API_KEY</code>
        </template>
      </i18n-t>
    </div>

    <template v-if="state?.configured">
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
        <span class="spacer" />
        <label class="scan">
          <BfIcon :path="mdiMagnify" :size="14" />
          <input
            v-model="query"
            type="search"
            :placeholder="t('tailnet.searchPlaceholder')"
            :aria-label="t('tailnet.searchPlaceholder')"
          />
        </label>
        <button
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

      <div v-else class="body" :class="{ 'with-dossier': selectedDevice }">
        <TailnetMap
          :devices="devices"
          :edges="edges"
          :internet="state.internet"
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
.scan {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.6rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-pill);
  background: var(--bf-surface-sunken);
  color: var(--bf-ink-faint);
  transition: border-color var(--bf-dur-150);
}
.scan:focus-within {
  border-color: var(--bf-line-hover);
}
.scan input {
  width: 9.5rem;
  border: none;
  background: transparent;
  outline: none;
  color: var(--bf-ink);
  font-family: var(--bf-font-mono);
  font-size: 0.72rem;
  letter-spacing: 0.04em;
}
.scan input::placeholder {
  color: var(--bf-ink-faint);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.62rem;
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

.body {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.9rem;
  align-items: stretch;
}
.body.with-dossier {
  grid-template-columns: minmax(0, 1fr) 21rem;
}
@media (max-width: 960px) {
  .body.with-dossier {
    grid-template-columns: 1fr;
  }
}

.no-uplink {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.9rem;
  padding: 3.2rem 1rem 3.6rem;
  border: 1px dashed var(--bf-line-strong);
  border-radius: var(--bf-radius-card);
  text-align: center;
}
.dish {
  width: 52px;
  height: 52px;
  border: 1px dashed var(--bf-ink-faint);
  border-radius: var(--bf-radius-pill);
  border-top-color: var(--bf-aurora-2);
  animation: bf-rotate 6s linear infinite;
}
.no-uplink-title {
  margin: 0;
  font-family: var(--bf-font-mono);
  font-size: 0.72rem;
  font-weight: 650;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--bf-ink-secondary);
}
.no-uplink-body {
  margin: 0;
  max-width: 34rem;
  font-size: 0.8rem;
  line-height: 1.6;
  color: var(--bf-ink-muted);
}
.no-uplink-body code {
  padding: 0.1rem 0.35rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
  background: var(--bf-surface-sunken);
  font-size: 0.7rem;
  color: var(--bf-ink-secondary);
}
</style>
