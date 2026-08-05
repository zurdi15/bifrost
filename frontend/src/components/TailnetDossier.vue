<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { mdiClose } from '@mdi/js';

import { INTERNET_ID, type TailnetDevice, type TailnetEdge } from '@/api/tailnet';
import BfStatusDot from '@/lib/data/BfStatusDot.vue';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import { formatDelta } from '@/utils/format';

const props = defineProps<{
  device: TailnetDevice;
  devices: TailnetDevice[];
  edges: TailnetEdge[];
}>();
const emit = defineEmits<{ close: []; select: [id: string] }>();

const { t } = useI18n();
const now = Math.floor(Date.now() / 1000);
const EXPIRY_SOON_S = 14 * 86400;

const byId = computed(() => new Map(props.devices.map((d) => [d.id, d])));

interface AccessRow {
  id: string;
  name: string;
  online: boolean | null;
  ports: string[];
  internet: boolean;
}

function toRow(id: string, ports: string[]): AccessRow {
  if (id === INTERNET_ID) {
    return { id, name: t('tailnet.internet'), online: null, ports, internet: true };
  }
  const peer = byId.value.get(id);
  return { id, name: peer?.name ?? id, online: peer?.online ?? null, ports, internet: false };
}

function sorted(rows: AccessRow[]): AccessRow[] {
  return rows.sort(
    (a, b) => Number(a.internet) - Number(b.internet) || a.name.localeCompare(b.name),
  );
}

const reaches = computed(() =>
  sorted(
    props.edges.filter((e) => e.src === props.device.id).map((e) => toRow(e.dst, e.ports)),
  ),
);
const reachedBy = computed(() =>
  sorted(
    props.edges.filter((e) => e.dst === props.device.id).map((e) => toRow(e.src, e.ports)),
  ),
);

const stateText = computed(() => {
  if (props.device.online) return t('tailnet.onlineState');
  if (!props.device.last_seen) return t('tailnet.offline');
  return t('tailnet.lastSeenAgo', { t: formatDelta(now - props.device.last_seen) });
});

const keyText = computed(() => {
  if (props.device.key_expiry_disabled || !props.device.expires) return t('tailnet.keyNever');
  const left = props.device.expires - now;
  if (left <= 0) return t('tailnet.keyExpired');
  return t('tailnet.keyExpiresIn', { t: formatDelta(left) });
});
const keyWarn = computed(
  () =>
    !props.device.key_expiry_disabled &&
    props.device.expires > 0 &&
    props.device.expires - now < EXPIRY_SOON_S,
);

function portLabel(port: string): string {
  return port === '*' ? t('tailnet.anyPort') : port;
}
</script>

<template>
  <aside class="dossier bf-slide-in-right" :aria-label="device.name">
    <p class="overline">{{ t('tailnet.dossier') }}</p>
    <header class="head">
      <BfStatusDot :status="device.online ? 'online' : 'offline'" :size="9" />
      <div class="who">
        <h3 class="name bf-metric">{{ device.name }}</h3>
        <p class="fqdn bf-metric">{{ device.fqdn }}</p>
      </div>
      <button class="close" type="button" :aria-label="t('tailnet.close')" @click="emit('close')">
        <BfIcon :path="mdiClose" :size="15" />
      </button>
    </header>

    <div class="chips">
      <BfChip v-for="tag in device.tags" :key="tag" mono>{{ tag }}</BfChip>
      <BfChip v-if="device.exit_node" tone="brand">{{ t('tailnet.exitNode') }}</BfChip>
      <BfChip v-if="device.external" tone="unknown">{{ t('tailnet.external') }}</BfChip>
      <BfChip v-if="device.blocks_incoming" tone="unknown">{{ t('tailnet.shieldsUp') }}</BfChip>
      <BfChip v-if="device.update_available" tone="warn">{{ t('tailnet.update') }}</BfChip>
      <BfChip v-if="keyWarn" tone="warn">{{ keyText }}</BfChip>
    </div>

    <dl class="facts">
      <div class="fact">
        <dt>{{ t('tailnet.factState') }}</dt>
        <dd>{{ stateText }}</dd>
      </div>
      <div class="fact">
        <dt>{{ t('tailnet.factAddresses') }}</dt>
        <dd class="bf-metric">
          <span v-for="ip in device.ips" :key="ip" class="ip">{{ ip }}</span>
        </dd>
      </div>
      <div v-if="device.os" class="fact">
        <dt>{{ t('tailnet.factOs') }}</dt>
        <dd>{{ device.os }}</dd>
      </div>
      <div v-if="device.user" class="fact">
        <dt>{{ t('tailnet.factOwner') }}</dt>
        <dd>{{ device.user }}</dd>
      </div>
      <div v-if="device.client_version" class="fact">
        <dt>{{ t('tailnet.factClient') }}</dt>
        <dd class="bf-metric">{{ device.client_version }}</dd>
      </div>
      <div class="fact">
        <dt>{{ t('tailnet.factKey') }}</dt>
        <dd :class="{ warn: keyWarn }">{{ keyText }}</dd>
      </div>
      <div v-if="device.routes.length" class="fact">
        <dt>{{ t('tailnet.factRoutes') }}</dt>
        <dd class="bf-metric">{{ device.routes.join(' · ') }}</dd>
      </div>
    </dl>

    <h4 class="access-title out">
      {{ t('tailnet.canReach') }}
      <span class="count bf-metric">{{ reaches.length }}</span>
    </h4>
    <p v-if="!reaches.length" class="none">{{ t('tailnet.noAccessOut') }}</p>
    <ul v-else class="access">
      <li v-for="row in reaches" :key="`out-${row.id}`" class="row">
        <button
          class="peer"
          type="button"
          :disabled="row.internet"
          @click="!row.internet && emit('select', row.id)"
        >
          <BfStatusDot
            v-if="row.online !== null"
            :status="row.online ? 'online' : 'offline'"
            :size="6"
          />
          <span class="peer-name" :class="{ mono: !row.internet }">{{ row.name }}</span>
        </button>
        <span class="ports">
          <BfChip v-for="port in row.ports.slice(0, 6)" :key="port" mono>
            {{ portLabel(port) }}
          </BfChip>
          <span v-if="row.ports.length > 6" class="more bf-metric">
            +{{ row.ports.length - 6 }}
          </span>
        </span>
      </li>
    </ul>

    <h4 class="access-title in">
      {{ t('tailnet.visibleFrom') }}
      <span class="count bf-metric">{{ reachedBy.length }}</span>
    </h4>
    <p v-if="!reachedBy.length" class="none">{{ t('tailnet.noAccessIn') }}</p>
    <ul v-else class="access">
      <li v-for="row in reachedBy" :key="`in-${row.id}`" class="row">
        <button class="peer" type="button" @click="emit('select', row.id)">
          <BfStatusDot
            v-if="row.online !== null"
            :status="row.online ? 'online' : 'offline'"
            :size="6"
          />
          <span class="peer-name mono">{{ row.name }}</span>
        </button>
        <span class="ports">
          <BfChip v-for="port in row.ports.slice(0, 6)" :key="port" mono>
            {{ portLabel(port) }}
          </BfChip>
          <span v-if="row.ports.length > 6" class="more bf-metric">
            +{{ row.ports.length - 6 }}
          </span>
        </span>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.dossier {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
  padding: 0.9rem 1rem 1.1rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-card);
  background: var(--bf-surface);
  max-height: 100%;
  overflow-y: auto;
  box-sizing: border-box;
}
.overline {
  margin: 0;
  font-family: var(--bf-font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--bf-ink-faint);
}
.head {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
}
.head > :first-child {
  margin-top: 0.35rem;
}
.who {
  min-width: 0;
  flex: 1;
}
.name {
  margin: 0;
  font-size: 1.02rem;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--bf-ink-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fqdn {
  margin: 0.1rem 0 0;
  font-size: 0.66rem;
  color: var(--bf-ink-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.close {
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
  cursor: pointer;
  transition:
    color var(--bf-dur-150),
    border-color var(--bf-dur-150);
}
.close:hover {
  color: var(--bf-ink);
  border-color: var(--bf-line-strong);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.facts {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  border-top: 1px solid var(--bf-line);
  padding-top: 0.7rem;
}
.fact {
  display: grid;
  grid-template-columns: 5.4rem 1fr;
  gap: 0.6rem;
  align-items: baseline;
}
.fact dt {
  font-family: var(--bf-font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--bf-ink-faint);
}
.fact dd {
  margin: 0;
  font-size: 0.78rem;
  color: var(--bf-ink-secondary);
  min-width: 0;
  overflow-wrap: anywhere;
}
.fact dd.warn {
  color: var(--bf-status-warn);
}
.ip {
  display: block;
  font-size: 0.72rem;
}
.access-title {
  margin: 0.35rem 0 0;
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
  font-size: 0.62rem;
  font-weight: 650;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--bf-ink-muted);
  border-top: 1px solid var(--bf-line);
  padding-top: 0.7rem;
}
.access-title.out {
  color: var(--bf-aurora-2);
}
.access-title.in {
  color: var(--bf-aurora-4);
}
.count {
  color: var(--bf-ink-secondary);
}
.none {
  margin: 0;
  font-size: 0.72rem;
  color: var(--bf-ink-faint);
}
.access {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.peer {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.12rem 0.3rem;
  margin-left: -0.3rem;
  border: none;
  border-radius: var(--bf-radius-ctl);
  background: transparent;
  color: var(--bf-ink);
  font-size: 0.78rem;
  cursor: pointer;
  transition: background var(--bf-dur-150);
}
.peer:hover:not(:disabled) {
  background: var(--bf-brand-tint);
}
.peer:disabled {
  cursor: default;
  color: var(--bf-ink-muted);
}
.peer-name.mono {
  font-family: var(--bf-font-mono);
  font-size: 0.72rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.ports {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: auto;
  flex-wrap: wrap;
}
.ports :deep(.bf-chip) {
  font-size: 0.62rem;
  padding: 0.05rem 0.4rem;
}
.more {
  font-size: 0.62rem;
  color: var(--bf-ink-faint);
}
</style>
