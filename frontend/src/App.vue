<script setup lang="ts">
import { onMounted } from 'vue';

import AppLayout from '@/layouts/AppLayout.vue';
import { useLiveStore } from '@/stores/live';

const live = useLiveStore();
onMounted(() => live.connect());
</script>

<template>
  <AppLayout>
    <RouterView v-slot="{ Component }">
      <Transition name="bf-view">
        <component :is="Component" />
      </Transition>
    </RouterView>
  </AppLayout>
</template>
