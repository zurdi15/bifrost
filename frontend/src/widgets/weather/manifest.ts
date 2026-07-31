import type { WidgetManifest } from '@/widgets/registry';

export default {
  id: 'weather',
  titleKey: 'widgets.weather',
  sizes: ['1x1', '2x1'],
  defaultSize: '1x1',
  defaultConfig: { lat: 40.42, lon: -3.7, units: 'celsius' },
  fetchesData: true,
  component: () => import('./Widget.vue').then((m) => m.default),
  configComponent: () => import('./Config.vue').then((m) => m.default),
} satisfies WidgetManifest;
