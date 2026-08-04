<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import BfButton from '@/lib/primitives/BfButton.vue';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import { useUiStore } from '@/stores/ui';

interface AlertRule {
  id: number;
  name: string;
  kind: string;
  min_severity: string;
  notifier: string;
  target: string;
  cooldown_s: number;
  enabled: boolean;
}

const { t } = useI18n();
const ui = useUiStore();

const rules = ref<AlertRule[]>([]);
const feedback = ref('');
const draft = reactive({
  name: '',
  kind: '*',
  min_severity: 'warning',
  notifier: 'ntfy',
  target: '',
});

const KINDS = ['*', 'node.status', 'k8s.cronjob.run', 'disk.updated', 'endpoint.status', 'container.event'];

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) throw new Error(String(response.status));
  return response.status === 204 ? (undefined as T) : response.json();
}

async function load(): Promise<void> {
  rules.value = await api<AlertRule[]>('/alert-rules');
}
onMounted(load);

async function addRule(): Promise<void> {
  if (!draft.name.trim() || !draft.target.trim()) return;
  await api('/alert-rules', { method: 'POST', body: JSON.stringify(draft) });
  draft.name = '';
  draft.target = '';
  await load();
}

async function toggle(rule: AlertRule): Promise<void> {
  await api(`/alert-rules/${rule.id}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled: !rule.enabled }),
  });
  await load();
}

async function remove(rule: AlertRule): Promise<void> {
  await api(`/alert-rules/${rule.id}`, { method: 'DELETE' });
  await load();
}

async function test(rule: AlertRule): Promise<void> {
  feedback.value = '';
  try {
    await api(`/alert-rules/${rule.id}/test`, { method: 'POST' });
    feedback.value = t('alerts.testOk');
  } catch {
    feedback.value = t('alerts.testFail');
  }
}
</script>

<template>
  <section>
    <header class="section-head">
      <h2 class="title">{{ t('alerts.title') }}</h2>
      <span v-if="feedback" class="feedback bf-metric">{{ feedback }}</span>
    </header>

    <!-- Adding rules is a layout-edit affordance, like every other "add". -->
    <BfCard v-if="ui.editing" class="add">
      <form class="form" @submit.prevent="addRule">
        <input v-model="draft.name" class="field" :placeholder="t('alerts.name')" required />
        <select v-model="draft.kind" class="field">
          <option v-for="kind in KINDS" :key="kind" :value="kind">{{ kind }}</option>
        </select>
        <select v-model="draft.min_severity" class="field">
          <option value="warning">warning</option>
          <option value="info">info</option>
        </select>
        <select v-model="draft.notifier" class="field">
          <option value="ntfy">ntfy</option>
          <option value="webhook">webhook</option>
          <option value="telegram">telegram</option>
        </select>
        <input
          v-model="draft.target"
          class="field target bf-metric"
          :placeholder="
            draft.notifier === 'ntfy'
              ? 'https://ntfy.sh/mi-topic'
              : draft.notifier === 'telegram'
                ? 'chat id (p.ej. -100123456789)'
                : 'https://…/webhook'
          "
          required
        />
        <BfButton size="sm" variant="primary">{{ t('alerts.add') }}</BfButton>
      </form>
    </BfCard>

    <p v-if="rules.length === 0" class="empty">{{ t('alerts.empty') }}</p>

    <div class="rules bf-stagger">
      <BfCard v-for="(rule, i) in rules" :key="rule.id" class="rule" :style="{ '--i': i }">
        <span class="name">{{ rule.name }}</span>
        <BfChip tone="brand" mono>{{ rule.kind }}</BfChip>
        <BfChip :tone="rule.min_severity === 'warning' ? 'warn' : 'neutral'">
          ≥ {{ rule.min_severity }}
        </BfChip>
        <BfChip mono>{{ rule.notifier }}</BfChip>
        <span class="target bf-metric">{{ rule.target }}</span>
        <span class="spacer" />
        <BfButton size="sm" @click="test(rule)">{{ t('alerts.test') }}</BfButton>
        <BfButton size="sm" @click="toggle(rule)">
          {{ rule.enabled ? t('alerts.disable') : t('alerts.enable') }}
        </BfButton>
        <BfButton size="sm" @click="remove(rule)">✕</BfButton>
      </BfCard>
    </div>
  </section>
</template>

<style scoped>
.section-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0 1.1rem;
}
.title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--bf-ink-secondary);
}
.feedback {
  font-size: 0.75rem;
  color: var(--bf-brand);
}
.add {
  margin-bottom: 1rem;
}
.form {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
  align-items: center;
}
.field {
  font: inherit;
  font-size: 0.8rem;
  padding: 0.32rem 0.6rem;
  background: var(--bf-surface-sunken);
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
  color: var(--bf-ink);
}
.field:focus {
  border-color: var(--bf-brand);
  outline: none;
}
.target {
  min-width: 16rem;
  flex: 1;
}
.empty {
  color: var(--bf-ink-muted);
  padding: 2rem 0;
  text-align: center;
}
.rules {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.rule {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.rule.name {
  font-weight: 600;
}
.name {
  font-weight: 600;
  color: var(--bf-ink-strong);
  font-size: 0.9rem;
}
.rule .target {
  font-size: 0.72rem;
  color: var(--bf-ink-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 24rem;
}
.spacer {
  flex: 1;
}
</style>
