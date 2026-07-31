<script setup lang="ts">
import AmbientSection from '@/components/AmbientSection.vue';
import BookmarksSection from '@/components/BookmarksSection.vue';
import ServicesSection from '@/components/ServicesSection.vue';
</script>

<template>
  <!-- The dashboard is what you *use*: services, bookmarks, widgets.
       Infrastructure health lives in its own Nodes section. -->
  <div class="dash">
    <div class="main">
      <ServicesSection />
      <BookmarksSection />
    </div>

    <AmbientSection class="aside" />
  </div>
</template>

<style scoped>
.dash {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0 2rem;
  align-items: start;
}
@media (min-width: 1100px) {
  .dash {
    grid-template-columns: minmax(0, 1fr) 300px;
  }
  .dash > .aside {
    position: sticky;
    top: 0.5rem;
    margin-top: 0;
  }
}
</style>
