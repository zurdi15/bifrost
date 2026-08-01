import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';
import Sortable from 'sortablejs';

import SortableList from './SortableList.vue';
import { useUiStore } from '@/stores/ui';

// Drive the component against a fake Sortable: unit tests can't perform real
// pointer drags, but they can pin the lifecycle (create/destroy on edit-mode
// toggles) and the onEnd contract (DOM revert + reorder emit) — which is
// exactly what silently broke with vuedraggable on Vue 3.5.
vi.mock('sortablejs', () => {
  const instances: FakeSortable[] = [];
  class FakeSortable {
    static created = instances;
    destroyed = false;
    constructor(
      public el: HTMLElement,
      public options: Record<string, unknown>,
    ) {
      instances.push(this);
    }
    static create(el: HTMLElement, options: Record<string, unknown>): FakeSortable {
      return new FakeSortable(el, options);
    }
    destroy(): void {
      this.destroyed = true;
    }
  }
  return { default: FakeSortable };
});

type FakeSortable = {
  el: HTMLElement;
  options: {
    onStart: () => void;
    onEnd: (evt: {
      item: HTMLElement;
      from: HTMLElement;
      oldIndex: number;
      newIndex: number;
    }) => void;
  };
  destroyed: boolean;
};
const created = (Sortable as unknown as { created: FakeSortable[] }).created;

interface Row {
  id: string;
}

function mountList(disabled = false) {
  return mount(SortableList, {
    // Generic component props defeat test-utils' inference — silence it.
    props: {
      items: [{ id: 'a' }, { id: 'b' }, { id: 'c' }] as Row[],
      idOf: (row: Row) => row.id,
      disabled,
    } as never,
    slots: { item: '<div class="row" /> ' },
    attachTo: document.body,
  });
}

const alive = () => created.filter((s) => !s.destroyed);

describe('SortableList', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    created.length = 0;
  });

  it('renders one slot item per element', () => {
    const wrapper = mountList();
    expect(wrapper.findAll('.row')).toHaveLength(3);
  });

  it('creates Sortable only while edit mode is on', async () => {
    const ui = useUiStore();
    const wrapper = mountList();
    expect(alive()).toHaveLength(0);

    ui.editing = true;
    await nextTick();
    expect(alive()).toHaveLength(1);
    expect(wrapper.classes()).toContain('bf-sorting');

    ui.editing = false;
    await nextTick();
    expect(alive()).toHaveLength(0);
    expect(wrapper.classes()).not.toContain('bf-sorting');
  });

  it('never engages when the disabled prop is set', async () => {
    const ui = useUiStore();
    const wrapper = mountList(true);
    ui.editing = true;
    await nextTick();
    expect(alive()).toHaveLength(0);
    expect(wrapper.classes()).not.toContain('bf-sorting');
  });

  it('reverts the DOM move and emits the new id order on drop', async () => {
    const ui = useUiStore();
    const wrapper = mountList();
    ui.editing = true;
    await nextTick();

    const [instance] = alive();
    const from = instance!.el;
    const item = from.children[0] as HTMLElement;
    // Mimic Sortable: physically move row 0 after row 1, then report the drop.
    instance!.options.onStart();
    from.insertBefore(item, from.children[2] ?? null);
    instance!.options.onEnd({ item, from, oldIndex: 0, newIndex: 1 });

    // The DOM is back the way Vue rendered it (state drives the real reorder).
    expect(from.children[0]).toBe(item);
    expect(wrapper.emitted('reorder')).toEqual([[['b', 'a', 'c']]]);
  });
});
