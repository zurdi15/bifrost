import type { Meta, StoryObj } from '@storybook/vue3-vite';

import BfButton from './primitives/BfButton.vue';
import BfChip from './primitives/BfChip.vue';
import BfCard from './structural/BfCard.vue';
import BfSkeleton from './structural/BfSkeleton.vue';

const meta: Meta = {
  title: 'Design System/Visual Language',
};
export default meta;

export const Primitives: StoryObj = {
  render: () => ({
    components: { BfButton, BfChip, BfCard, BfSkeleton },
    template: `
      <div style="display:flex;flex-direction:column;gap:1.5rem;min-width:420px">
        <div style="display:flex;gap:.6rem;align-items:center">
          <BfButton variant="primary">Primary</BfButton>
          <BfButton>Ghost</BfButton>
          <BfButton size="sm">Small</BfButton>
          <BfButton disabled>Disabled</BfButton>
        </div>
        <div style="display:flex;gap:.5rem;flex-wrap:wrap">
          <BfChip tone="up">online</BfChip>
          <BfChip tone="warn">pending</BfChip>
          <BfChip tone="degraded">degraded</BfChip>
          <BfChip tone="down" mono>DOWN · 12:03:21</BfChip>
          <BfChip tone="brand">k3s</BfChip>
          <BfChip>neutral</BfChip>
        </div>
        <BfCard interactive>
          <strong style="color:var(--bf-ink-strong)">Interactive card</strong>
          <p style="margin:.4rem 0 0;color:var(--bf-ink-secondary);font-size:.85rem">
            Hover me — hairline border, lift and shadow.
          </p>
        </BfCard>
        <div style="display:flex;flex-direction:column;gap:.5rem">
          <BfSkeleton width="60%" height=".8rem" />
          <BfSkeleton width="90%" height=".8rem" />
          <BfSkeleton width="40%" height=".8rem" />
        </div>
      </div>
    `,
  }),
};
