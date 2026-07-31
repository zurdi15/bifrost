<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import BfButton from '@/lib/primitives/BfButton.vue';
import { useLiveStore } from '@/stores/live';

const { t } = useI18n();
const live = useLiveStore();

const open = ref(false);
const name = ref('');
const kind = ref<'http' | 'ping' | 'tcp'>('http');
const target = ref('');
const busy = ref(false);
const error = ref('');

async function submit(): Promise<void> {
  if (!name.value.trim() || !target.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    const response = await fetch('/api/v1/nodes/endpoints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.value.trim(),
        checks: [{ kind: kind.value, target: target.value.trim() }],
      }),
    });
    if (!response.ok) throw new Error(String(response.status));
    await live.snapshot();
    open.value = false;
    name.value = '';
    target.value = '';
  } catch {
    error.value = t('endpoint.error');
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="endpoint-form">
    <BfButton size="sm" @click="open = !open">+ {{ t('endpoint.add') }}</BfButton>

    <form v-if="open" class="form bf-rise-in" @submit.prevent="submit">
      <input
        v-model="name"
        class="field"
        :placeholder="t('endpoint.name')"
        required
      />
      <select v-model="kind" class="field kind">
        <option value="http">http</option>
        <option value="ping">ping</option>
        <option value="tcp">tcp</option>
      </select>
      <input
        v-model="target"
        class="field target bf-metric"
        :placeholder="
          kind === 'http' ? 'http://haos:8123/manifest.json' : kind === 'tcp' ? 'host:port' : 'host'
        "
        required
      />
      <BfButton size="sm" variant="primary" :disabled="busy">{{ t('endpoint.save') }}</BfButton>
      <span v-if="error" class="error">{{ error }}</span>
    </form>
  </div>
</template>

<style scoped>
.endpoint-form {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.form {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.field {
  font: inherit;
  font-size: 0.8rem;
  padding: 0.32rem 0.6rem;
  background: var(--bf-surface-sunken);
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
  color: var(--bf-ink);
  transition: border-color var(--bf-dur-150);
}
.field:focus {
  border-color: var(--bf-brand);
  outline: none;
}
.field::placeholder {
  color: var(--bf-ink-faint);
}
.kind {
  width: 5.2rem;
}
.target {
  min-width: 16rem;
}
.error {
  color: var(--bf-status-down);
  font-size: 0.75rem;
}
</style>
