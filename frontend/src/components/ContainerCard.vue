<script setup lang="ts">
import { computed, reactive, ref, watch, watchEffect } from 'vue';
import { useI18n } from 'vue-i18n';
import { mdiOpenInNew, mdiPackageUp, mdiPencil, mdiServer } from '@mdi/js';

import { api } from '@/api/client';
import type { ContainerInfo } from '@/api/types';
import BfButton from '@/lib/primitives/BfButton.vue';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import BfStatusDot from '@/lib/data/BfStatusDot.vue';
import { useIconStore } from '@/stores/icons';
import { useLiveStore } from '@/stores/live';
import { useUiStore } from '@/stores/ui';
import { formatBytes } from '@/utils/format';

const props = defineProps<{ container: ContainerInfo }>();

const { t } = useI18n();
const live = useLiveStore();
const icons = useIconStore();
const ui = useUiStore();

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

const stateLabel = computed(() =>
  props.container.health === 'unhealthy' ? 'unhealthy' : (props.container.state ?? 'unknown'),
);

// Live usage line: pct for docker, millicores for k8s, bytes for both.
const usage = computed(() => {
  const container = props.container;
  const parts: string[] = [];
  if (container.cpu_pct !== null && container.cpu_pct !== undefined) {
    parts.push(`${container.cpu_pct.toFixed(1)}%`);
  } else if (container.cpu_millis !== null && container.cpu_millis !== undefined) {
    parts.push(`${container.cpu_millis}m`);
  }
  if (container.mem_bytes !== null && container.mem_bytes !== undefined) {
    parts.push(formatBytes(container.mem_bytes, 0));
  }
  return parts.join(' · ');
});

const displayName = computed(() => props.container.meta.name || props.container.name);
const iconIsImage = computed(() => /^(https?:\/\/|\/)/.test(props.container.meta.icon ?? ''));

// No explicit icon → resolve one from the service name (selfh.st via hub).
watchEffect(() => {
  if (!props.container.meta.icon && props.container.source !== 'node') {
    icons.ensure(props.container);
  }
});
const autoIcon = computed(() =>
  props.container.meta.icon ? null : icons.iconFor(props.container),
);
const autoIconBroken = ref(false);
watch(autoIcon, () => (autoIconBroken.value = false));

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
    <BfCard
      :interactive="!editing && !!container.meta.url"
      class="container-card"
      :class="{
        'is-down': status === 'offline' || status === 'disabled',
        'node-ui': container.source === 'node',
      }"
    >
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
        <!-- The dot IS the state — top-right, details on hover. An update
             upstream is a quiet package glyph beside it. -->
        <span
          v-if="container.update"
          class="update-wrap bf-tip-bl"
          :data-bf-tip="`→ ${container.update}`"
        >
          <BfIcon :path="mdiPackageUp" :size="14" />
        </span>
        <span class="dot-wrap bf-tip-bl" :data-bf-tip="stateLabel">
          <BfStatusDot :status="status" :desync-id="container.id" :size="9" />
        </span>
        <!-- k8s services take their meta from labels/annotations, not UI edits.
             Customization is an edit-mode affordance, not everyday chrome. -->
        <button
          v-if="ui.editing && container.source === 'docker'"
          class="edit"
          type="button"
          :aria-label="t('service.edit')"
          @click="openEdit"
        >
          <BfIcon :path="mdiPencil" :size="12" />
        </button>
        <div class="head">
          <span v-if="container.meta.icon" class="icon">
            <img v-if="iconIsImage" :src="container.meta.icon" alt="" loading="lazy" />
            <template v-else>{{ container.meta.icon }}</template>
          </span>
          <span v-else-if="container.source === 'node'" class="icon node-glyph">
            <BfIcon :path="mdiServer" :size="20" />
          </span>
          <span v-else-if="autoIcon && !autoIconBroken" class="icon">
            <img :src="autoIcon" alt="" loading="lazy" @error="autoIconBroken = true" />
          </span>
          <div class="id">
            <span class="name" :data-bf-tip="container.name">
              <span class="name-text">{{ displayName }}</span>
              <BfIcon v-if="container.meta.url" :path="mdiOpenInNew" :size="12" class="ext" />
            </span>
            <p class="image bf-metric" :data-bf-tip="container.image ?? undefined">
              <span class="image-text">{{ shortImage }}</span>
            </p>
          </div>
        </div>
        <footer class="foot">
          <span v-if="usage && status === 'online'" class="usage bf-metric">{{ usage }}</span>
          <BfChip v-if="container.meta.hide" tone="unknown">{{ t('service.hidden') }}</BfChip>
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
  gap: 0.55rem;
  padding: 0.8rem 0.85rem;
}
/* Lift the hovered card above its siblings so the tooltip never hides. */
.container-card:hover {
  z-index: 5;
}
/* Down services fade back; the dot stays at full strength. */
.is-down > :not(.dot-wrap) {
  opacity: 0.55;
}
.usage {
  font-size: 0.68rem;
  color: var(--bf-ink-muted);
}
.update-wrap {
  position: absolute;
  top: 2rem;
  right: 0.6rem;
  display: inline-flex;
  color: var(--bf-status-warn);
}
.dot-wrap {
  position: absolute;
  top: 0.65rem;
  right: 0.7rem;
  display: inline-flex;
}
.head {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  min-width: 0;
  /* keep clear of the corner dot */
  padding-right: 1.1rem;
}
/* The icon is the face of the card. */
.icon {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  font-size: 1.5rem;
  line-height: 1;
}
.icon img {
  width: 34px;
  height: 34px;
  max-width: 100%;
  object-fit: contain;
  border-radius: var(--bf-radius-ctl);
}
.id {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
/* Truncation lives on the inner text spans: the outer elements carry the
   styled tooltip (::after), which overflow:hidden would clip. */
.name {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--bf-ink-strong);
  min-width: 0;
  max-width: 100%;
}
.name-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ext {
  flex: none;
  color: var(--bf-ink-faint);
}
.image {
  margin: 0;
  font-size: 0.66rem;
  color: var(--bf-ink-muted);
}
.node-glyph {
  color: var(--bf-ink-muted);
}
.image-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Node UIs are machines, not apps: rack-strip look — accent edge, tinted
   surface, no footer (the name IS the node). */
.container-card.node-ui {
  border-inline-start: 2px solid var(--bf-brand);
  background: color-mix(in srgb, var(--bf-brand-tint) 30%, var(--bf-surface));
}
.container-card.node-ui .foot {
  display: none;
}
.container-card.node-ui .image {
  color: var(--bf-ink-muted);
}
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  min-height: 1rem;
}
.node {
  font-size: 0.68rem;
  color: var(--bf-ink-faint);
}
/* Customize affordance: only rendered in global edit mode. */
.edit {
  position: absolute;
  bottom: 0.5rem;
  right: 0.5rem;
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
  transition:
    color var(--bf-dur-150),
    border-color var(--bf-dur-150);
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
