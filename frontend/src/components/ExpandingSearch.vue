<script setup lang="ts">
import { ref } from 'vue';
import { mdiMagnify } from '@mdi/js';

import BfIcon from '@/lib/primitives/BfIcon.vue';

defineProps<{ placeholder: string; label: string }>();

// One persistent pill: the magnifier is always there and the field grows out
// of it / shrinks back into it — no element swap, both directions animated
// (a deliberate exception to the no-exit-animations rule).
// The query lives in the parent (it filters the section); closing always
// clears it so a filter never survives invisibly.
const model = defineModel<string>({ required: true });
const open = ref(false);
const inputEl = ref<HTMLInputElement | null>(null);

function toggle(): void {
  if (open.value) {
    close();
  } else {
    open.value = true;
    inputEl.value?.focus();
  }
}
function close(): void {
  open.value = false;
  model.value = '';
  inputEl.value?.blur();
}
function onBlur(): void {
  if (open.value && model.value.trim() === '') close();
}
</script>

<template>
  <span class="search" :class="{ open }">
    <input
      ref="inputEl"
      v-model="model"
      class="search-input"
      type="search"
      :placeholder="placeholder"
      :aria-label="label"
      :aria-hidden="!open"
      :tabindex="open ? undefined : -1"
      @keydown.esc="close"
      @blur="onBlur"
    />
    <!-- mousedown.prevent keeps the input focused so blur-close and the
         click toggle never race (empty field + click would reopen). -->
    <button
      class="search-btn"
      type="button"
      :aria-label="label"
      :aria-expanded="open"
      @mousedown.prevent
      @click="toggle"
    >
      <BfIcon :path="mdiMagnify" :size="14" />
    </button>
  </span>
</template>

<style scoped>
.search {
  display: inline-flex;
  align-items: center;
  /* Fixed height matching the dashboard toolbar pills, so the row never
     changes height when neighboring controls appear or vanish. */
  height: 1.65rem;
  padding: 0 0.25rem;
  border: 1px solid var(--bf-line);
  border-radius: var(--bf-radius-pill);
  background: transparent;
  transition: border-color var(--bf-dur-150);
}
.search:hover {
  border-color: var(--bf-line-hover);
}
.search.open {
  border-color: var(--bf-brand);
}
/* The input is bare — the pill is the field. Width is the one sanctioned
   layout transition here: it's what makes the same element morph. */
.search-input {
  width: 0;
  padding: 0;
  opacity: 0;
  font: inherit;
  font-size: 0.75rem;
  border: none;
  background: transparent;
  color: var(--bf-ink);
  outline: none;
  transition:
    width var(--bf-dur-300) var(--bf-ease-spring),
    padding var(--bf-dur-300) var(--bf-ease-spring),
    opacity var(--bf-dur-150);
}
.search.open .search-input {
  width: 11rem;
  padding-left: 0.4rem;
  opacity: 1;
}
.search-input:focus-visible {
  outline: none;
  box-shadow: none;
}
.search-input::placeholder {
  color: var(--bf-ink-faint);
}
.search-input::-webkit-search-cancel-button {
  display: none;
}
.search-btn {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.25rem;
  border: none;
  background: transparent;
  color: var(--bf-ink-muted);
  cursor: pointer;
  transition: color var(--bf-dur-150);
}
.search:hover .search-btn {
  color: var(--bf-ink);
}
.search.open .search-btn {
  color: var(--bf-brand);
}
</style>
