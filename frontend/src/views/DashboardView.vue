<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import AmbientSection from '@/components/AmbientSection.vue';
import BookmarksSection from '@/components/BookmarksSection.vue';
import ServicesSection from '@/components/ServicesSection.vue';
import { useLayoutStore } from '@/stores/layout';
import { useUiStore } from '@/stores/ui';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

// The active tab lives in the URL (/#bookmarks) so both are deep-linkable.
const tab = computed<'services' | 'bookmarks'>({
  get: () => (route.hash === '#bookmarks' ? 'bookmarks' : 'services'),
  set: (value) =>
    void router.replace({ hash: value === 'bookmarks' ? '#bookmarks' : '' }),
});

const ui = useUiStore();
const layout = useLayoutStore();
// No widgets → give services the full width. Edit mode always shows the
// rail so widgets can be added in the first place.
const showAside = computed(() => ui.editing || layout.ambient.length > 0);
</script>

<template>
  <!-- The dashboard is what you *use*: services, bookmarks, widgets.
       Infrastructure health lives in its own Nodes section. -->
  <div class="dash" :class="{ 'with-aside': showAside }">
    <div class="main">
      <nav class="tabs" role="tablist">
        <button
          class="tab"
          :class="{ active: tab === 'services' }"
          role="tab"
          :aria-selected="tab === 'services'"
          @click="tab = 'services'"
        >
          {{ t('services.title') }}
        </button>
        <button
          class="tab"
          :class="{ active: tab === 'bookmarks' }"
          role="tab"
          :aria-selected="tab === 'bookmarks'"
          @click="tab = 'bookmarks'"
        >
          {{ t('bookmarks.title') }}
        </button>
      </nav>

      <ServicesSection v-if="tab === 'services'" embedded />
      <BookmarksSection v-else embedded />
    </div>

    <AmbientSection v-if="showAside" class="aside" />
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: 0.3rem;
  margin: 1rem 0 0.2rem;
}
.tab {
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 0.3rem 0.85rem;
  border: none;
  border-radius: var(--bf-radius-ctl);
  background: transparent;
  color: var(--bf-ink-muted);
  cursor: pointer;
  transition:
    color var(--bf-dur-150),
    background-color var(--bf-dur-150);
}
.tab:hover {
  color: var(--bf-ink);
  background: var(--bf-surface-raised);
}
.tab.active {
  color: var(--bf-brand);
  background: var(--bf-brand-tint);
}
.dash {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0 2rem;
  align-items: start;
}
@media (min-width: 1100px) {
  .dash.with-aside {
    grid-template-columns: minmax(0, 1fr) 300px;
  }
  .dash > .aside {
    position: sticky;
    top: 0.5rem;
    margin-top: 0;
  }
}
</style>
