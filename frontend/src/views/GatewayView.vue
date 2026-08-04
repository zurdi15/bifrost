<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import BfChip from '@/lib/primitives/BfChip.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import BfStatusDot from '@/lib/data/BfStatusDot.vue';
import { useLiveStore } from '@/stores/live';

interface RouteCheck {
  ok: boolean;
  status: number | null;
  latency_ms: number | null;
  cert_days: number | null;
  checked_at: number;
}

interface GatewayRoute {
  host: string;
  node: string;
  port: number;
  container: string;
  source: 'explicit' | 'derived';
  hide: boolean;
  path?: string | null;
  check?: RouteCheck | null;
}

interface GatewayExcluded {
  container: string;
  node: string;
  reason: string;
  detail?: string;
}

interface GatewayIngress {
  host: string;
  namespace: string;
  name: string;
  tls: boolean;
}

interface GatewayReport {
  domain: string;
  routes: GatewayRoute[];
  excluded: GatewayExcluded[];
  ingresses: GatewayIngress[];
}

const { t } = useI18n();

function checkTip(check: RouteCheck): string {
  if (!check.ok) return t('gateway.down');
  const parts = [`HTTP ${check.status}`];
  if (check.latency_ms != null) parts.push(`${Math.round(check.latency_ms)} ms`);
  if (check.cert_days != null) parts.push(`cert ${check.cert_days}d`);
  return parts.join(' · ');
}
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
          <!-- The l-* groups are invisible on desktop (display: contents keeps
               today's single line) and become predictable rows on mobile:
               host / tags + check / container·node·port. -->
          <div class="row">
            <span class="l-host">
              <a
                class="host"
                :href="`https://${route.host}${route.path ?? ''}`"
                target="_blank"
                rel="noopener"
              >
                {{ route.host }}<span v-if="route.path" class="path">{{ route.path }}</span>
              </a>
            </span>
            <span class="l-tags">
              <BfChip :tone="route.source === 'derived' ? 'unknown' : 'neutral'">
                {{ route.source === 'derived' ? t('gateway.derived') : t('gateway.explicit') }}
              </BfChip>
              <BfChip v-if="route.hide" tone="warn">{{ t('gateway.hidden') }}</BfChip>
            </span>
            <span class="spacer" />
            <span class="l-where">
              <span class="where">{{ route.container }}</span>
              <BfChip tone="neutral" mono>{{ route.node }}</BfChip>
              <span class="port bf-metric">:{{ route.port }}</span>
            </span>
            <span class="l-check">
              <span
                v-if="route.check"
                class="bf-tip-bottom check-dot"
                :data-bf-tip="checkTip(route.check)"
              >
                <BfStatusDot :status="route.check.ok ? 'online' : 'offline'" :size="8" />
              </span>
              <span
                v-if="route.check?.ok && route.check.latency_ms != null"
                class="latency bf-metric"
              >
                {{ Math.round(route.check.latency_ms) }} ms
              </span>
              <BfChip
                v-if="route.check?.cert_days != null && route.check.cert_days <= 14"
                tone="warn"
                mono
              >
                cert {{ route.check.cert_days }}d
              </BfChip>
            </span>
          </div>
        </BfCard>
      </div>

      <h3 class="subtitle">
        {{ t('gateway.cluster') }}
        <span class="count bf-metric">{{ report.ingresses.length }}</span>
      </h3>
      <p v-if="loaded && report.ingresses.length === 0" class="empty">
        {{ t('gateway.noIngresses') }}
      </p>
      <div v-else class="list bf-stagger">
        <BfCard
          v-for="(ingress, i) in report.ingresses"
          :key="`${ingress.namespace}/${ingress.name}/${ingress.host}`"
          :padded="false"
          :style="{ '--i': i }"
        >
          <div class="row">
            <span class="l-host">
              <a class="host" :href="`https://${ingress.host}`" target="_blank" rel="noopener">
                {{ ingress.host }}
              </a>
            </span>
            <span class="l-tags">
              <BfChip tone="neutral">Ingress</BfChip>
            </span>
            <span class="spacer" />
            <span class="l-where">
              <span class="where">{{ ingress.namespace }}/{{ ingress.name }}</span>
            </span>
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
            <span class="l-host">
              <span class="name">{{ item.container }}</span>
            </span>
            <span class="l-tags">
              <BfChip tone="neutral" mono>{{ item.node }}</BfChip>
            </span>
            <span class="spacer" />
            <span class="l-where">
              <span class="reason">{{ t(`gateway.reasons.${item.reason}`) }}</span>
              <span v-if="item.detail" class="detail bf-metric">{{ item.detail }}</span>
            </span>
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
.path {
  color: var(--bf-ink-muted);
  font-weight: 500;
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
.check-dot {
  display: inline-flex;
  align-items: center;
}
.latency {
  font-size: 0.72rem;
  color: var(--bf-ink-muted);
}
/* Desktop: the l-* groups dissolve — children join the row's single flex
   line exactly as before. */
.l-host,
.l-tags,
.l-where,
.l-check {
  display: contents;
}
/* Narrow screens: free-wrapping made every card wrap differently (and could
   orphan the check dot on its own line). Fixed rows instead:
     1. host / container name
     2. tags on the left, check dot + latency on the right
     3. container · node · port  (or reason · detail)               */
@media (max-width: 720px) {
  .row {
    row-gap: 0.6rem;
    padding: 0.8rem 0.95rem;
  }
  .spacer {
    display: none;
  }
  .l-host {
    display: flex;
    flex-basis: 100%;
    min-width: 0;
    order: 0;
  }
  .host,
  .name {
    font-size: 0.95rem;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .l-tags {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    order: 1;
  }
  .l-check {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    margin-left: auto;
    order: 2;
  }
  .l-where {
    display: flex;
    flex-basis: 100%;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.3rem 0.5rem;
    min-width: 0;
    order: 3;
  }
  .where {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .reason {
    flex-basis: 100%;
  }
}
</style>
