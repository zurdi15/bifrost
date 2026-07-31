<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { mdiOpenInNew, mdiPencil } from '@mdi/js';

import { api } from '@/api/client';
import type { ContainerInfo } from '@/api/types';
import BfButton from '@/lib/primitives/BfButton.vue';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import BfStatusDot from '@/lib/data/BfStatusDot.vue';
import { useLiveStore } from '@/stores/live';

const props = defineProps<{ container: ContainerInfo }>();

const { t } = useI18n();
const live = useLiveStore();

// Container state/health → the shared node-status visual language.
const status = computed(() => {
  if (props.container.health === 'unhealthy') return 'degraded';
  switch (props.container.state) {
    case 'running':
      return 'online';
    case 'restarting':
    case 'starting':
      return 'pending';
    case 'paused':
      return 'disabled';
    default:
      return 'offline';
  }
});

const tone = computed(
  () =>
    ((
      {
        online: 'up',
        degraded: 'degraded',
        pending: 'warn',
        disabled: 'unknown',
        offline: 'down',
      } as const
    )[status.value] ?? 'unknown'),
);

const shortImage = computed(() => {
  const image = props.container.image ?? '';
  return image.split('/').pop()?.split('@')[0] ?? image;
});

const displayName = computed(() => props.container.meta.name || props.container.name);
const iconIsImage = computed(() => /^(https?:\/\/|\/)/.test(props.container.meta.icon ?? ''));

// ── customize (name/icon/url/group/hide overrides) ─────────────────────────
const editing = ref(false);
const busy = ref(false);
const form = reactive({ name: '', icon: '', url: '', group: '', hide: false });

function openEdit(eventArg: Event): void {
  eventArg.preventDefault();
  eventArg.stopPropagation();
  form.name = props.container.meta.name ?? '';
  form.icon = props.container.meta.icon ?? '';
  form.url = props.container.meta.url ?? '';
  form.group = props.container.meta.group ?? '';
  form.hide = props.container.meta.hide ?? false;
  editing.value = true;
}

async function save(): Promise<void> {
  busy.value = true;
  try {
    await api.putServiceMeta(props.container.node_uuid, props.container.name, { ...form });
    await live.snapshot();
    editing.value = false;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <component
    :is="container.meta.url && !editing ? 'a' : 'div'"
    :href="editing ? undefined : container.meta.url"
    target="_blank"
    rel="noreferrer"
    class="wrap"
  >
    <BfCard :interactive="!editing && !!container.meta.url" class="container-card">
      <form v-if="editing" class="edit-form" @submit.prevent="save" @click.stop>
        <input v-model="form.name" class="field" :placeholder="t('service.name')" />
        <input v-model="form.icon" class="field bf-metric" :placeholder="t('service.icon')" />
        <input v-model="form.url" class="field bf-metric" :placeholder="t('service.url')" />
        <input v-model="form.group" class="field" :placeholder="t('service.group')" />
        <label class="hide-row">
          <input v-model="form.hide" type="checkbox" />
          {{ t('service.hide') }}
        </label>
        <span class="edit-actions">
          <BfButton size="sm" variant="ghost" type="button" @click="editing = false">
            {{ t('service.cancel') }}
          </BfButton>
          <BfButton size="sm" variant="primary" :disabled="busy">
            {{ t('service.save') }}
          </BfButton>
        </span>
      </form>

      <template v-else>
        <button class="edit" type="button" :aria-label="t('service.edit')" @click="openEdit">
          <BfIcon :path="mdiPencil" :size="12" />
        </button>
        <header class="head">
          <BfStatusDot :status="status" :desync-id="container.id" :size="8" />
          <span v-if="container.meta.icon" class="icon">
            <img v-if="iconIsImage" :src="container.meta.icon" alt="" loading="lazy" />
            <template v-else>{{ container.meta.icon }}</template>
          </span>
          <span class="name" :title="container.name">{{ displayName }}</span>
          <BfChip v-if="container.meta.hide" tone="unknown">{{ t('service.hidden') }}</BfChip>
          <BfIcon v-if="container.meta.url" :path="mdiOpenInNew" :size="13" class="ext" />
        </header>
        <p class="image bf-metric" :title="container.image ?? ''">{{ shortImage }}</p>
        <footer class="foot">
          <BfChip :tone="tone">
            {{ container.health === 'unhealthy' ? 'unhealthy' : container.state }}
          </BfChip>
          <span class="node">{{ container.node_name }}</span>
        </footer>
      </template>
    </BfCard>
  </component>
</template>

<style scoped>
.wrap {
  text-decoration: none;
  color: inherit;
  display: block;
  border-radius: var(--bf-radius-card);
}
.container-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  padding: 0.75rem 0.85rem;
}
.head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}
.icon {
  flex: none;
  display: inline-flex;
  align-items: center;
  font-size: 0.95rem;
  line-height: 1;
}
.icon img {
  width: 18px;
  height: 18px;
  max-width: 100%;
  object-fit: contain;
  border-radius: var(--bf-radius-ctl);
}
.name {
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--bf-ink-strong);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ext {
  color: var(--bf-ink-faint);
}
.image {
  margin: 0;
  font-size: 0.68rem;
  color: var(--bf-ink-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.node {
  font-size: 0.68rem;
  color: var(--bf-ink-faint);
}
/* Customize affordance: revealed on hover, always visible on touch. */
.edit {
  position: absolute;
  top: 0.45rem;
  right: 0.45rem;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
  background: var(--bf-surface-raised);
  color: var(--bf-ink-secondary);
  cursor: pointer;
  opacity: 0;
  transition:
    opacity var(--bf-dur-150),
    color var(--bf-dur-150),
    border-color var(--bf-dur-150);
}
.container-card:hover .edit,
.edit:focus-visible {
  opacity: 1;
}
@media (hover: none) {
  .edit {
    opacity: 1;
  }
}
.edit:hover {
  color: var(--bf-ink);
  border-color: var(--bf-line-hover);
}
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.field {
  font: inherit;
  font-size: 0.78rem;
  padding: 0.3rem 0.55rem;
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
.hide-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.75rem;
  color: var(--bf-ink-secondary);
  cursor: pointer;
}
.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.4rem;
}
</style>
