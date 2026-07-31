<script setup lang="ts">
import { reactive } from 'vue';
import { useI18n } from 'vue-i18n';

import BfButton from '@/lib/primitives/BfButton.vue';

const props = defineProps<{ config: Record<string, unknown> }>();
const emit = defineEmits<{ save: [config: Record<string, unknown>] }>();

const { t } = useI18n();
const draft = reactive({
  base_url: String(props.config.base_url ?? 'http://homeassistant:8123'),
  token: String(props.config.token ?? ''),
  entities: ((props.config.entities as string[]) ?? []).join('\n'),
});

function save(): void {
  emit('save', {
    base_url: draft.base_url.trim(),
    token: draft.token.trim(),
    entities: draft.entities
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean),
  });
}
</script>

<template>
  <form class="config" @submit.prevent="save">
    <label class="field-label">
      url
      <input v-model="draft.base_url" class="field bf-metric" placeholder="http://homeassistant:8123" />
    </label>
    <label class="field-label">
      token
      <input v-model="draft.token" type="password" class="field bf-metric" autocomplete="off" />
    </label>
    <label class="field-label wide">
      {{ t('widgets.haEntities') }}
      <textarea
        v-model="draft.entities"
        class="field bf-metric"
        rows="3"
        placeholder="sensor.processor_use&#10;sensor.memory_use_percent"
      />
    </label>
    <BfButton size="sm" variant="primary">{{ t('widgets.save') }}</BfButton>
  </form>
</template>

<style scoped>
.config {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.field-label {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.62rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--bf-ink-muted);
}
.wide {
  width: 100%;
}
.field {
  font: inherit;
  font-size: 0.78rem;
  padding: 0.28rem 0.5rem;
  background: var(--bf-surface-sunken);
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
  color: var(--bf-ink);
}
.field:focus {
  border-color: var(--bf-brand);
  outline: none;
}
textarea.field {
  resize: vertical;
  width: 100%;
  box-sizing: border-box;
}
</style>
