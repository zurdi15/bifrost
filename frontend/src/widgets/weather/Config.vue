<script setup lang="ts">
import { reactive } from 'vue';
import { useI18n } from 'vue-i18n';

import BfButton from '@/lib/primitives/BfButton.vue';

const props = defineProps<{ config: Record<string, unknown> }>();
const emit = defineEmits<{ save: [config: Record<string, unknown>] }>();

const { t } = useI18n();
const draft = reactive({
  lat: Number(props.config.lat ?? 40.42),
  lon: Number(props.config.lon ?? -3.7),
});
</script>

<template>
  <form class="config" @submit.prevent="emit('save', { ...config, ...draft })">
    <label class="field-label">
      lat
      <input v-model.number="draft.lat" type="number" step="0.01" min="-90" max="90" class="field bf-metric" />
    </label>
    <label class="field-label">
      lon
      <input v-model.number="draft.lon" type="number" step="0.01" min="-180" max="180" class="field bf-metric" />
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
.field {
  font: inherit;
  font-size: 0.78rem;
  width: 6rem;
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
</style>
