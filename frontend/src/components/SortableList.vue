<script setup lang="ts" generic="T">
import { shallowRef, watchEffect } from 'vue';
import draggable from 'vuedraggable';

import { useUiStore } from '@/stores/ui';

const props = defineProps<{
  items: T[];
  idOf: (item: T) => string;
}>();
const emit = defineEmits<{ reorder: [ids: string[]] }>();

const ui = useUiStore();

// vuedraggable mutates its list in place, and live updates keep replacing
// props.items — keep a local copy, frozen while a drag is in flight so a
// metrics tick can't cancel the gesture halfway.
const local = shallowRef<T[]>([...props.items]);
let dragging = false;
watchEffect(() => {
  const next = [...props.items];
  if (!dragging) local.value = next;
});

function onStart(): void {
  dragging = true;
}

function onEnd(): void {
  dragging = false;
  emit('reorder', local.value.map(props.idOf));
}
</script>

<template>
  <!-- Keyed by mode: Sortable only honors `disabled` reliably at create
       time, so toggling edit mode rebuilds the instance instead of praying
       for option reactivity. -->
  <draggable
    :key="ui.editing ? 'sortable-on' : 'sortable-off'"
    :list="local"
    :item-key="idOf"
    :disabled="!ui.editing"
    :animation="200"
    ghost-class="bf-drag-ghost"
    :class="{ 'bf-sorting': ui.editing }"
    @start="onStart"
    @end="onEnd"
  >
    <template #item="{ element, index }">
      <slot name="item" :element="element" :index="index" />
    </template>
  </draggable>
</template>
