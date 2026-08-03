<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import BfChip from '@/lib/primitives/BfChip.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import { useLiveStore } from '@/stores/live';

interface GatewayRoute {
  host: string;
  node: string;
  port: number;
  container: string;
  source: 'explicit' | 'derived';
  hide: boolean;
}

interface GatewayExcluded {
  container: string;
  node: string;
  reason: string;
  detail?: string;
}

interface GatewayReport {
  domain: string;
  routes: GatewayRoute[];
  excluded: GatewayExcluded[];
}

const { t } = useI18n();
const live = useLiveStore();

const report = ref<GatewayReport | null>(null);
const loaded = ref(false);

async function load(): Promise<void> {
  try {
    const response = await fetch('/api/v1/gateway/report');
    if (response.ok) report.value = await response.json();
  } finally {
    loaded.value = true;
  }
}

onMounted(load);
// Reload when routing inputs change, not on every stats tick: the fingerprint
// only tracks fields the gateway analysis reads.
const fingerprint = computed(() =>
  [...live.containers.values()]
    .flat()
    .map((s) => `${s.node_uuid}/${s.name}:${s.meta.url ?? ''}:${(s.ports ?? []).join()}`)
    .sort()
    .join('|'),
);
watch(fingerprint, load);
watch(() => live.k8sVersion, load);
</script>

<template>
  <section>
    <header class="section-head">
      <h2 class="title">{{ t('gateway.title') }}</h2>
      <span class="head-chips">
        <BfChip v-if="report?.domain" tone="up" mono>*.{{ report.domain }}</BfChip>
      </span>
    </header>

    <p v-if="loaded && report && !report.domain" class="empty">{{ t('gateway.noDomain') }}</p>

    <template v-if="report?.domain">
      <h3 class="subtitle">
        {{ t('gateway.routed') }}
        <span class="count bf-metric">{{ report.routes.length }}</span>
      </h3>
      <p v-if="loaded && report.routes.length === 0" class="empty">{{ t('gateway.noRoutes') }}</p>
      <div class="list bf-stagger">
        <BfCard
          v-for="(route, i) in report.routes"
          :key="route.host"
          :padded="false"
          :style="{ '--i': i }"
        >
          <div class="row">
            <a class="host" :href="`https://${route.host}`" target="_blank" rel="noopener">
              {{ route.host }}
            </a>
            <BfChip :tone="route.source === 'derived' ? 'unknown' : 'neutral'">
              {{ route.source === 'derived' ? t('gateway.derived') : t('gateway.explicit') }}
            </BfChip>
            <BfChip v-if="route.hide" tone="warn">{{ t('gateway.hidden') }}</BfChip>
            <span class="spacer" />
            <span class="where">{{ route.container }}</span>
            <BfChip tone="neutral" mono>{{ route.node }}</BfChip>
            <span class="port bf-metric">:{{ route.port }}</span>
          </div>
        </BfCard>
      </div>

      <h3 class="subtitle">
        {{ t('gateway.excluded') }}
        <span class="count bf-metric">{{ report.excluded.length }}</span>
      </h3>
      <p v-if="loaded && report.excluded.length === 0" class="empty">
        {{ t('gateway.allRouted') }}
      </p>
      <div v-else class="list bf-stagger">
        <BfCard
          v-for="(item, i) in report.excluded"
          :key="`${item.node}/${item.container}`"
          :padded="false"
          :style="{ '--i': i }"
        >
          <div class="row">
            <span class="name">{{ item.container }}</span>
            <BfChip tone="neutral" mono>{{ item.node }}</BfChip>
            <span class="spacer" />
            <span class="reason">{{ t(`gateway.reasons.${item.reason}`) }}</span>
            <span v-if="item.detail" class="detail bf-metric">{{ item.detail }}</span>
          </div>
        </BfCard>
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
.subtitle {
  margin: 1.4rem 0 0.7rem;
  font-size: 0.72rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--bf-ink-muted);
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}
.count {
  color: var(--bf-ink-secondary);
  font-size: 0.72rem;
}
.empty {
  color: var(--bf-ink-muted);
  padding: 1.6rem 0;
  text-align: center;
}
.list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.7rem 1rem;
  flex-wrap: wrap;
}
.host {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--bf-ink-strong);
  text-decoration: none;
}
.host:hover {
  text-decoration: underline;
}
.name {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--bf-ink-strong);
}
.spacer {
  flex: 1;
}
.where {
  font-size: 0.78rem;
  color: var(--bf-ink-secondary);
}
.port {
  font-size: 0.78rem;
  color: var(--bf-ink-secondary);
}
.reason {
  font-size: 0.78rem;
  color: var(--bf-ink-secondary);
}
.detail {
  font-size: 0.72rem;
  color: var(--bf-ink-muted);
}
</style>
