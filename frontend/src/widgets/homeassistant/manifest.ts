import type { WidgetManifest } from '@/widgets/registry';

export default {
  id: 'homeassistant',
  titleKey: 'widgets.ha',
  sizes: ['1x1', '2x1'],
  defaultSize: '1x1',
  defaultConfig: { base_url: 'http://homeassistant:8123', token: '', entities: [] },
  fetchesData: true,
  component: () => import('./Widget.vue').then((m) => m.default),
  configComponent: () => import('./Config.vue').then((m) => m.default),
} satisfies WidgetManifest;
