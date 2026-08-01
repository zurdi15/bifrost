<script setup lang="ts" generic="T">
import { computed } from 'vue';
import draggable from 'vuedraggable';

import { useUiStore } from '@/stores/ui';

const props = defineProps<{
  items: T[];
  idOf: (item: T) => string;
}>();
const emit = defineEmits<{ reorder: [ids: string[]] }>();

const ui = useUiStore();

// vuedraggable mutates the bound array in place — hand it a copy that
// rebuilds whenever the source list changes.
const local = computed(() => [...props.items]);
</script>

<template>
  <draggable
    :list="local"
    :item-key="idOf"
    :disabled="!ui.editing"
    :animation="200"
    ghost-class="bf-drag-ghost"
    :class="{ 'bf-sorting': ui.editing }"
    @end="emit('reorder', local.map(idOf))"
  >
    <template #item="{ element, index }">
      <slot name="item" :element="element" :index="index" />
    </template>
  </draggable>
</template>
