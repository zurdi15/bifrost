<script setup lang="ts" generic="T">
import Sortable from 'sortablejs';
import { onBeforeUnmount, ref, shallowRef, watch, watchEffect } from 'vue';

import { useUiStore } from '@/stores/ui';

const props = withDefaults(
  defineProps<{
    items: T[];
    idOf: (item: T) => string;
    /** Keep the grid but refuse drags (e.g. non-canonical group-by views). */
    disabled?: boolean;
  }>(),
  { disabled: false },
);
const emit = defineEmits<{ reorder: [ids: string[]] }>();

const ui = useUiStore();
const root = ref<HTMLElement | null>(null);

// Live ticks replace props.items every few seconds — freeze the rendered list
// while a drag is in flight so a metrics update can't cancel the gesture.
const display = shallowRef<T[]>(props.items);
let dragging = false;
watchEffect(() => {
  const next = props.items;
  if (!dragging) display.value = next;
});

// vuedraggable is unmaintained and silently broken against Vue 3.5, so we
// drive Sortable by hand: an instance exists only while edit mode is on.
let sortable: Sortable | null = null;

function create(el: HTMLElement): void {
  sortable = Sortable.create(el, {
    animation: 200,
    ghostClass: 'bf-drag-ghost',
    // Touch: hold briefly to lift, so the page still scrolls normally.
    delay: 150,
    delayOnTouchOnly: true,
    onStart: () => {
      dragging = true;
    },
    onEnd: (evt) => {
      const { item, from, oldIndex, newIndex } = evt;
      if (oldIndex == null || newIndex == null) {
        dragging = false;
        return;
      }
      // Sortable moved the real DOM node; put it back where Vue's vdom
      // expects it and let the new order flow back down through props.
      item.remove();
      from.insertBefore(item, from.children[oldIndex] ?? null);
      const ids = display.value.map(props.idOf);
      dragging = false;
      if (oldIndex === newIndex) return;
      const [moved] = ids.splice(oldIndex, 1);
      ids.splice(newIndex, 0, moved!);
      emit('reorder', ids);
    },
  });
}

watch(
  () => [ui.editing && !props.disabled, root.value] as const,
  ([active, el]) => {
    if (active && el && !sortable) {
      create(el);
    } else if ((!active || !el) && sortable) {
      sortable.destroy();
      sortable = null;
    }
  },
  { immediate: true, flush: 'post' },
);
onBeforeUnmount(() => sortable?.destroy());
</script>

<template>
  <div ref="root" :class="{ 'bf-sorting': ui.editing && !disabled }">
    <template v-for="(element, index) in display" :key="idOf(element)">
      <slot name="item" :element="element" :index="index" />
    </template>
  </div>
</template>
