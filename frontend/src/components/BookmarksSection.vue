<script setup lang="ts">
import { computed, onMounted, reactive, ref, watchEffect } from 'vue';
import { useI18n } from 'vue-i18n';
import { mdiPencil } from '@mdi/js';

import { api } from '@/api/client';
import type { BookmarkInfo } from '@/api/types';
import BfButton from '@/lib/primitives/BfButton.vue';
import BfIcon from '@/lib/primitives/BfIcon.vue';
import { useIconStore } from '@/stores/icons';

const { t } = useI18n();
const icons = useIconStore();

const bookmarks = ref<BookmarkInfo[]>([]);
const loaded = ref(false);

// null → closed · 0 → creating · id → editing that bookmark.
const editing = ref<number | null>(null);
const busy = ref(false);
const form = reactive({ name: '', url: '', icon: '', group: '' });

onMounted(async () => {
  try {
    bookmarks.value = await api.bookmarks();
  } finally {
    loaded.value = true;
  }
});

watchEffect(() => {
  for (const bookmark of bookmarks.value) {
    if (!bookmark.icon) icons.ensure({ name: bookmark.name });
  }
});

const groups = computed(() => {
  const map = new Map<string, BookmarkInfo[]>();
  for (const bookmark of bookmarks.value) {
    const key = bookmark.group ?? '';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(bookmark);
  }
  return [...map.entries()].sort(([a], [b]) =>
    a === '' ? 1 : b === '' ? -1 : a.localeCompare(b),
  );
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
    <header class="section-head">
      <h2 class="title">{{ t('bookmarks.title') }}</h2>
      <span class="head-actions">
        <BfButton
          size="sm"
          :variant="editing === 0 ? 'ghost' : undefined"
          @click="editing = editing === 0 ? null : (openCreate(), 0)"
        >
          {{ editing === 0 ? `✕ ${t('bookmarks.cancel')}` : `+ ${t('bookmarks.add')}` }}
        </BfButton>
      </span>
    </header>

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

    <p v-if="bookmarks.length === 0" class="empty">{{ t('bookmarks.empty') }}</p>

    <div v-for="[group, list] in groups" :key="group || '_'" class="group">
      <h3 v-if="group" class="group-title">{{ group }}</h3>
      <div class="grid bf-stagger">
        <a
          v-for="(bookmark, i) in list"
          :key="bookmark.id"
          :href="bookmark.url"
          target="_blank"
          rel="noreferrer"
          class="bookmark"
          :style="{ '--i': i }"
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
          <button
            class="edit"
            type="button"
            :aria-label="t('bookmarks.edit')"
            @click="openEdit(bookmark, $event)"
          >
            <BfIcon :path="mdiPencil" :size="11" />
          </button>
        </a>
      </div>
    </div>
  </section>
</template>

<style scoped>
.bookmarks {
  margin-top: 2rem;
}
.section-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0 1.1rem;
  flex-wrap: wrap;
}
.head-actions {
  margin-left: auto;
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
  margin-bottom: 1rem;
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
  opacity: 0;
  transition:
    opacity var(--bf-dur-150),
    color var(--bf-dur-150);
}
.bookmark:hover .edit,
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
}
</style>
