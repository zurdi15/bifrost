import type { Meta, StoryObj } from '@storybook/vue3-vite';
import { ref } from 'vue';

import BfGauge from './BfGauge.vue';
import BfNumberRoll from './BfNumberRoll.vue';
import BfSparkline from './BfSparkline.vue';
import BfStatusDot from './BfStatusDot.vue';

const meta: Meta = {
  title: 'Design System/Data',
};
export default meta;

const wave = (n: number, phase = 0) =>
  Array.from({ length: n }, (_, i) => 50 + 35 * Math.sin(i / 5 + phase) + Math.random() * 8);

export const StatusHeartbeat: StoryObj = {
  render: () => ({
    components: { BfStatusDot },
    template: `
      <div style="display:flex;gap:1.6rem;align-items:center">
        <BfStatusDot status="online" desync-id="mimir" />
        <BfStatusDot status="online" desync-id="freyja" />
        <BfStatusDot status="online" desync-id="odin" />
        <BfStatusDot status="degraded" desync-id="d" />
        <BfStatusDot status="offline" desync-id="e" />
      </div>
    `,
  }),
};

export const Gauges: StoryObj = {
  render: () => ({
    components: { BfGauge },
    setup() {
      const value = ref(37);
      setInterval(() => (value.value = Math.random() * 100), 2500);
      return { value };
    },
    template: `
      <div style="display:flex;gap:1.4rem">
        <BfGauge :value="value" label="cpu" color="var(--bf-metric-cpu)" />
        <BfGauge :value="62" label="mem" color="var(--bf-metric-mem)" />
        <BfGauge :value="82" label="warn" />
        <BfGauge :value="96" label="danger" />
      </div>
    `,
  }),
};

export const Sparklines: StoryObj = {
  render: () => ({
    components: { BfSparkline },
    setup: () => ({ points: wave(60), flat: wave(30, 2) }),
    template: `
      <div style="display:flex;flex-direction:column;gap:1.2rem">
        <BfSparkline :points="points" :width="240" :height="48" color="var(--bf-metric-cpu)" />
        <BfSparkline :points="flat" :width="240" :height="48" flatline />
      </div>
    `,
  }),
};

export const Odometer: StoryObj = {
  render: () => ({
    components: { BfNumberRoll },
    setup() {
      const value = ref(37);
      setInterval(() => (value.value = Math.floor(Math.random() * 1000)), 1800);
      return { value };
    },
    template: `
      <div style="font-size:2.4rem;color:var(--bf-ink-strong)">
        <BfNumberRoll :value="value" />
      </div>
    `,
  }),
};
