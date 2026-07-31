import type { Preview } from '@storybook/vue3-vite';
import { createPinia } from 'pinia';
import { setup } from '@storybook/vue3-vite';

import { i18n } from '../src/i18n';

import '@fontsource-variable/schibsted-grotesk';
import '@fontsource-variable/jetbrains-mono';
import '../src/styles/global.css';

setup((app) => {
  app.use(createPinia());
  app.use(i18n);
});

const preview: Preview = {
  parameters: {
    backgrounds: {
      options: {
        bifrost: { name: 'bifrost', value: '#0a0d16' },
      },
    },
    layout: 'centered',
  },
  initialGlobals: {
    backgrounds: { value: 'bifrost' },
  },
};

export default preview;
