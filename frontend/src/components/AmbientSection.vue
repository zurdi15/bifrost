<script setup lang="ts">
import { computed, onMounted, ref, shallowRef, watch, type Component } from 'vue';
import { useI18n } from 'vue-i18n';
import { mdiClose, mdiChevronLeft, mdiChevronRight, mdiCog, mdiPencil, mdiResize } from '@mdi/js';

import BfButton from '@/lib/primitives/BfButton.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import { WIDGETS, type WidgetSize } from '@/widgets/registry';

interface WidgetRow {
  id: number;
  type: string;
  config: Record<string, unknown>;
}

interface LayoutEntry {
  id: number;
  size: WidgetSize;
}

const { t } = useI18n();

const widgets = ref<WidgetRow[]>([]);
const layout = ref<LayoutEntry[]>([]);
const editing = ref(false);
const configOpen = ref<number | null>(null);
const components = shallowRef(new Map<string, Component>());
const configComponents = shallowRef(new Map<string, Component>());

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) throw new Error(`${path} → ${response.status}`);
  return response.status === 204 ? (undefined as T) : response.json();
}

async function ensureComponent(type: string): Promise<void> {
  const manifest = WIDGETS[type];
  if (!manifest || components.value.has(type)) return;
  const loaded = await manifest.component();
  components.value.set(type, loaded);
  components.value = new Map(components.value);
  if (manifest.configComponent) {
    configComponents.value.set(type, await manifest.configComponent());
    configComponents.value = new Map(configComponents.value);
  }
}

onMounted(async () => {
  const [rows, saved] = await Promise.all([
    api<WidgetRow[]>('/widgets'),
    api<{ ambient?: LayoutEntry[] }>('/dashboard'),
  ]);
  widgets.value = rows;
  const known = new Set(rows.map((row) => row.id));
  layout.value = (saved.ambient ?? []).filter((entry) => known.has(entry.id));
  // Widgets created but missing from the layout (e.g. older sessions) append.
  for (const row of rows) {
    if (!layout.value.some((entry) => entry.id === row.id)) {
      layout.value.push({ id: row.id, size: WIDGETS[row.type]?.defaultSize ?? '1x1' });
    }
  }
  await Promise.all(rows.map((row) => ensureComponent(row.type)));
});

let saveTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  layout,
  () => {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      void api('/dashboard', {
        method: 'PUT',
        body: JSON.stringify({ ambient: layout.value }),
      });
    }, 800);
  },
  { deep: true },
);

const entries = computed(() =>
  layout.value
    .map((entry) => ({
      entry,
      widget: widgets.value.find((w) => w.id === entry.id),
    }))
    .filter((x): x is { entry: LayoutEntry; widget: WidgetRow } => !!x.widget),
);

async function addWidget(type: string): Promise<void> {
  const manifest = WIDGETS[type];
  const created = await api<WidgetRow>('/widgets', {
    method: 'POST',
    body: JSON.stringify({ type, config: manifest.defaultConfig }),
  });
  widgets.value.push(created);
  layout.value.push({ id: created.id, size: manifest.defaultSize });
  await ensureComponent(type);
}

async function removeWidget(id: number): Promise<void> {
  await api(`/widgets/${id}`, { method: 'DELETE' });
  widgets.value = widgets.value.filter((w) => w.id !== id);
  layout.value = layout.value.filter((entry) => entry.id !== id);
}

function move(id: number, delta: number): void {
  const index = layout.value.findIndex((entry) => entry.id === id);
  const target = index + delta;
  if (index < 0 || target < 0 || target >= layout.value.length) return;
  const next = [...layout.value];
  [next[index], next[target]] = [next[target], next[index]];
  layout.value = next;
}

function cycleSize(entry: LayoutEntry, type: string): void {
  const sizes = WIDGETS[type]?.sizes ?? ['1x1'];
  entry.size = sizes[(sizes.indexOf(entry.size) + 1) % sizes.length];
}

async function saveConfig(widget: WidgetRow, config: Record<string, unknown>): Promise<void> {
  const updated = await api<WidgetRow>(`/widgets/${widget.id}`, {
    method: 'PATCH',
    body: JSON.stringify({ config }),
  });
  widget.config = updated.config;
  configOpen.value = null;
}
</script>

<template>
  <section class="ambient">
    <header class="section-head">
      <h2 class="title">{{ t('widgets.title') }}</h2>
      <span class="actions">
        <template v-if="editing">
          <BfButton
            v-for="(manifest, type) in WIDGETS"
            :key="type"
            size="sm"
            @click="addWidget(String(type))"
          >
            + {{ t(manifest.titleKey) }}
          </BfButton>
        </template>
        <BfButton size="sm" :variant="editing ? 'primary' : 'ghost'" @click="editing = !editing">
          <BfIcon :path="mdiPencil" :size="13" />
          {{ editing ? t('widgets.done') : t('widgets.edit') }}
        </BfButton>
      </span>
    </header>

    <p v-if="entries.length === 0" class="empty">{{ t('widgets.empty') }}</p>

    <TransitionGroup tag="div" class="grid" name="bf-grid" appear>
      <BfCard
        v-for="{ entry, widget } in entries"
        :key="widget.id"
        class="cell"
        :class="[`s-${entry.size}`, { editing }]"
      >
        <div v-if="editing" class="controls">
          <button class="ctl" type="button" @click="move(widget.id, -1)" :aria-label="t('widgets.left')">
            <BfIcon :path="mdiChevronLeft" :size="14" />
          </button>
          <button class="ctl" type="button" @click="cycleSize(entry, widget.type)" aria-label="size">
            <BfIcon :path="mdiResize" :size="13" />
          </button>
          <button
            v-if="configComponents.get(widget.type)"
            class="ctl"
            type="button"
            @click="configOpen = configOpen === widget.id ? null : widget.id"
            aria-label="config"
          >
            <BfIcon :path="mdiCog" :size="13" />
          </button>
          <button class="ctl" type="button" @click="move(widget.id, 1)" :aria-label="t('widgets.right')">
            <BfIcon :path="mdiChevronRight" :size="14" />
          </button>
          <button class="ctl danger" type="button" @click="removeWidget(widget.id)" aria-label="remove">
            <BfIcon :path="mdiClose" :size="13" />
          </button>
        </div>

        <component
          :is="configComponents.get(widget.type)"
          v-if="editing && configOpen === widget.id && configComponents.get(widget.type)"
          :config="widget.config"
          @save="saveConfig(widget, $event)"
        />
        <component
          :is="components.get(widget.type)"
          v-else-if="components.get(widget.type)"
          :widget-id="widget.id"
          :config="widget.config"
        />
      </BfCard>
    </TransitionGroup>
  </section>
</template>

<style scoped>
.ambient {
  margin-top: 2rem;
}
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
.actions {
  margin-left: auto;
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.empty {
  color: var(--bf-ink-muted);
  font-size: 0.85rem;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.9rem;
}
.cell {
  position: relative;
}
.s-2x1 {
  /* Full row rather than span 2: the grid may be a single column when the
     section sits in the dashboard's side rail. */
  grid-column: 1 / -1;
}
.cell.editing {
  border-style: dashed;
  border-color: var(--bf-line-hover);
}
/* FLIP reorder via TransitionGroup. */
.bf-grid-move {
  transition: transform var(--bf-dur-300) var(--bf-ease-spring);
}
.bf-grid-enter-active {
  animation: bf-rise-in var(--bf-dur-300) var(--bf-ease-spring) both;
}
.bf-grid-leave-active {
  display: none;
}
.controls {
  position: absolute;
  top: 0.4rem;
  right: 0.4rem;
  display: flex;
  gap: 0.2rem;
  z-index: 2;
}
.ctl {
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
.ctl:hover {
  color: var(--bf-ink);
  border-color: var(--bf-line-hover);
}
.ctl.danger:hover {
  color: var(--bf-status-down);
  border-color: var(--bf-status-down);
}
</style>
