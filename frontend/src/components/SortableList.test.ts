import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it } from 'vitest';
import { nextTick } from 'vue';
import draggable from 'vuedraggable';

import SortableList from './SortableList.vue';
import { useUiStore } from '@/stores/ui';

interface Row {
  id: string;
}

function mountList() {
  return mount(SortableList, {
    // Generic component props defeat test-utils' inference — silence it.
    props: {
      items: [{ id: 'a' }, { id: 'b' }] as Row[],
      idOf: (row: Row) => row.id,
    } as never,
    slots: { item: '<div class="row" />' },
  });
}

function sortableDisabled(wrapper: ReturnType<typeof mountList>): unknown {
  const vm = wrapper.findComponent(draggable).vm as unknown as {
    _sortable?: { option: (name: string) => unknown };
  };
  return vm._sortable?.option('disabled');
}

describe('SortableList', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('renders one slot item per element', () => {
    const wrapper = mountList();
    expect(wrapper.findAll('.row')).toHaveLength(2);
  });

  it('enables dragging when edit mode turns on after mount', async () => {
    // Regression: Sortable was created disabled (edit off at mount) and the
    // option never updated, so dragging could not be engaged at all.
    const ui = useUiStore();
    const wrapper = mountList();
    expect(sortableDisabled(wrapper)).toBe(true);

    ui.editing = true;
    await nextTick();
    expect(sortableDisabled(wrapper)).toBe(false);
    // Re-query: the mode toggle remounts the root element.
    expect(wrapper.findComponent(draggable).classes()).toContain('bf-sorting');

    ui.editing = false;
    await nextTick();
    expect(sortableDisabled(wrapper)).toBe(true);
  });
});
