import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import BfNumberRoll from './BfNumberRoll.vue';

function digitOffsets(wrapper: ReturnType<typeof mount>): number[] {
  return wrapper.findAll('.col').map((col) => {
    const match = /translateY\(-(\d+)em\)/.exec(col.attributes('style') ?? '');
    return match ? Number(match[1]) : -1;
  });
}

describe('BfNumberRoll', () => {
  it('exposes the value accessibly', () => {
    const wrapper = mount(BfNumberRoll, { props: { value: 42, suffix: '%' } });
    expect(wrapper.attributes('aria-label')).toBe('42%');
  });

  it('rolls each digit column to its value', async () => {
    const wrapper = mount(BfNumberRoll, { props: { value: 37 } });
    // Mount starts at 0 and rolls in on the next frame.
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    await wrapper.vm.$nextTick();
    expect(digitOffsets(wrapper)).toEqual([3, 7]);
  });

  it('updates columns when the value changes', async () => {
    const wrapper = mount(BfNumberRoll, { props: { value: 10 } });
    await wrapper.setProps({ value: 25 });
    await wrapper.vm.$nextTick();
    expect(digitOffsets(wrapper)).toEqual([2, 5]);
    expect(wrapper.attributes('aria-label')).toBe('25');
  });

  it('renders decimals with a static separator', async () => {
    const wrapper = mount(BfNumberRoll, { props: { value: 3.5, decimals: 1 } });
    await wrapper.setProps({ value: 4.2 });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('.');
    expect(digitOffsets(wrapper)).toEqual([4, 2]);
  });
});
