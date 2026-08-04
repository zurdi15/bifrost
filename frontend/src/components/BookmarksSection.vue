<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch, watchEffect } from 'vue';
import { useI18n } from 'vue-i18n';
import { mdiPencil } from '@mdi/js';

import { api } from '@/api/client';
import type { BookmarkInfo } from '@/api/types';
import SortableList from '@/components/SortableList.vue';
import BfButton from '@/lib/primitives/BfButton.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import { useDashboardStore } from '@/stores/dashboard';
import { useIconStore } from '@/stores/icons';
import { useLiveStore } from '@/stores/live';
import { useUiStore } from '@/stores/ui';

// embedded: rendered under the dashboard tabs, which already label it.
withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false });

const { t } = useI18n();
const icons = useIconStore();
const live = useLiveStore();
const ui = useUiStore();
const dash = useDashboardStore();

const bookmarks = ref<BookmarkInfo[]>([]);
const loaded = ref(false);

// null → closed · 0 → creating · id → editing that bookmark.
const editing = ref<number | null>(null);
const busy = ref(false);
const form = reactive({ name: '', url: '', icon: '', group: '' });

async function refresh(): Promise<void> {
  try {
    bookmarks.value = await api.bookmarks();
  } finally {
    loaded.value = true;
  }
}

onMounted(refresh);
// bookmarks.yml resynced on the hub → reload.
watch(() => live.bookmarksVersion, () => void refresh());

watchEffect(() => {
  for (const bookmark of bookmarks.value) {
    if (!bookmark.icon) icons.ensure({ name: bookmark.name });
  }
});

// The search query comes from the dashboard toolbar, shared across tabs.
const visible = computed(() =>
  bookmarks.value.filter(
    (bookmark) =>
      !dash.needle ||
      [bookmark.name, bookmark.url, bookmark.group].some((field) =>
        field?.toLowerCase().includes(dash.needle),
      ),
  ),
);

const groups = computed(() => {
  const map = new Map<string, BookmarkInfo[]>();
  // Case-insensitive buckets; the first spelling seen is the shown label.
  const labels = new Map<string, string>();
  for (const bookmark of visible.value) {
    const key = (bookmark.group ?? '').toLowerCase();
    if (!labels.has(key)) labels.set(key, bookmark.group ?? '');
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(bookmark);
  }
  return [...map.entries()]
    .sort(([a], [b]) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)))
    .map(([key, list]) => [key, labels.get(key) ?? key, list] as const);
});

function iconOf(bookmark: BookmarkInfo): string | null {
  return bookmark.icon ?? icons.iconFor({ name: bookmark.name });
}

function isImage(icon: string): boolean {
  return /^(https?:\/\/|\/)/.test(icon);
}

function openCreate(): void {
  form.name = '';
  form.url = '';
  form.icon = '';
  form.group = '';
  editing.value = 0;
}

function openEdit(bookmark: BookmarkInfo, eventArg: Event): void {
  eventArg.preventDefault();
  eventArg.stopPropagation();
  form.name = bookmark.name;
  form.url = bookmark.url;
  form.icon = bookmark.icon ?? '';
  form.group = bookmark.group ?? '';
  editing.value = bookmark.id;
}

async function save(): Promise<void> {
  if (!form.name.trim() || !form.url.trim()) return;
  busy.value = true;
  try {
    if (editing.value === 0) {
      await api.createBookmark({ ...form });
    } else if (editing.value !== null) {
      await api.patchBookmark(editing.value, { ...form });
    }
    bookmarks.value = await api.bookmarks();
    editing.value = null;
  } finally {
    busy.value = false;
  }
}

const bookmarkId = (bookmark: BookmarkInfo): string => String(bookmark.id);

// Reorder within a group: PUT the full new global order in one call — the
// hub renumbers everything and mirrors it into bookmarks.yml.
async function reorderGroup(group: string, ids: string[]): Promise<void> {
  const byId = new Map(bookmarks.value.map((b) => [String(b.id), b]));
  const newGroupOrder = ids
    .map((id) => byId.get(id))
    .filter((b): b is BookmarkInfo => !!b);
  const sequence = groups.value.flatMap(([g, , list]) =>
    g === group ? newGroupOrder : list,
  );
  await api.orderBookmarks(sequence.map((b) => b.id));
  bookmarks.value = await api.bookmarks();
}

async function remove(): Promise<void> {
  if (!editing.value) return;
  busy.value = true;
  try {
    await api.deleteBookmark(editing.value);
    bookmarks.value = await api.bookmarks();
    editing.value = null;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section v-if="loaded" class="bookmarks">
    <header v-if="!embedded" class="section-head">
      <h2 class="title">{{ t('bookmarks.title') }}</h2>
    </header>

    <p v-if="bookmarks.length === 0" class="empty">{{ t('bookmarks.empty') }}</p>
    <p v-else-if="visible.length === 0" class="empty">{{ t('bookmarks.noMatches') }}</p>

    <div v-for="[group, label, list] in groups" :key="group || '_'" class="group">
      <h3 v-if="label" class="group-title">{{ label }}</h3>
      <SortableList
        class="grid bf-stagger"
        :items="list"
        :id-of="bookmarkId"
        :disabled="dash.needle !== ''"
        @reorder="(ids) => void reorderGroup(group, ids)"
      >
        <template #item="{ element: bookmark, index: i }">
        <a
          :href="bookmark.url"
          target="_blank"
          rel="noreferrer"
          class="bookmark"
          :style="{ '--i': i }"
          :data-bf-tip="bookmark.url"
        >
          <span v-if="iconOf(bookmark)" class="icon">
            <img
              v-if="isImage(iconOf(bookmark)!)"
              :src="iconOf(bookmark)!"
              alt=""
              loading="lazy"
            />
            <template v-else>{{ iconOf(bookmark) }}</template>
          </span>
          <span class="name">{{ bookmark.name }}</span>
          <!-- Edits write through to bookmarks.yml on the hub;
               customization only surfaces in global edit mode. -->
          <button
            v-if="ui.editing"
            class="edit"
            type="button"
            :aria-label="t('bookmarks.edit')"
            @click="openEdit(bookmark, $event)"
          >
            <BfIcon :path="mdiPencil" :size="11" />
          </button>
        </a>
        </template>
      </SortableList>
    </div>

    <!-- Creating and editing both happen down here, next to the button. -->
    <form
      v-if="editing !== null"
      class="form bf-rise-in"
      @submit.prevent="save"
      @keydown.esc="editing = null"
    >
      <input v-model="form.name" class="field" :placeholder="t('bookmarks.name')" required />
      <input
        v-model="form.url"
        class="field url bf-metric"
        :placeholder="t('bookmarks.url')"
        required
      />
      <input v-model="form.icon" class="field" :placeholder="t('bookmarks.icon')" />
      <input v-model="form.group" class="field" :placeholder="t('bookmarks.group')" />
      <BfButton size="sm" variant="primary" :disabled="busy">{{ t('bookmarks.save') }}</BfButton>
      <BfButton
        v-if="editing !== 0"
        size="sm"
        variant="ghost"
        type="button"
        :disabled="busy"
        class="danger"
        @click="remove"
      >
        {{ t('bookmarks.remove') }}
      </BfButton>
    </form>

    <footer v-if="ui.editing" class="foot">
      <BfButton
        size="sm"
        :variant="editing === 0 ? 'ghost' : undefined"
        @click="editing = editing === 0 ? null : (openCreate(), 0)"
      >
        {{ editing === 0 ? `✕ ${t('bookmarks.cancel')}` : `+ ${t('bookmarks.add')}` }}
      </BfButton>
    </footer>
  </section>
</template>

<style scoped>
.bookmarks {
  margin-top: 0;
}
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
.form {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
  margin-top: 1.2rem;
}
.foot {
  display: flex;
  justify-content: flex-start;
  margin-top: 1.2rem;
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
.url {
  min-width: 14rem;
}
.danger:hover {
  color: var(--bf-status-down);
}
.empty {
  color: var(--bf-ink-muted);
  font-size: 0.85rem;
}
.group + .group {
  margin-top: 1.1rem;
}
.group-title {
  margin: 0 0 0.6rem;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--bf-ink-muted);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 0.55rem;
}
.bookmark {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
  background: var(--bf-surface);
  text-decoration: none;
  color: var(--bf-ink);
  transition:
    border-color var(--bf-dur-150),
    background-color var(--bf-dur-150);
}
.bookmark:hover {
  border-color: var(--bf-line-hover);
  background: var(--bf-surface-raised);
}
.icon {
  flex: none;
  display: inline-flex;
  align-items: center;
  font-size: 0.9rem;
  line-height: 1;
}
.icon img {
  width: 16px;
  height: 16px;
  object-fit: contain;
}
.name {
  font-size: 0.8rem;
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.edit {
  position: absolute;
  top: 50%;
  right: 0.4rem;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-ctl);
  background: var(--bf-surface-raised);
  color: var(--bf-ink-secondary);
  cursor: pointer;
  transition: color var(--bf-dur-150);
}
.edit:hover {
  color: var(--bf-ink);
}
</style>
