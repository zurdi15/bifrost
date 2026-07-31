import type { WidgetManifest } from '@/widgets/registry';

export default {
  id: 'clock',
  titleKey: 'widgets.clock',
  sizes: ['1x1', '2x1'],
  defaultSize: '1x1',
  defaultConfig: { show_seconds: true },
  fetchesData: false,
  component: () => import('./Widget.vue').then((m) => m.default),
} satisfies WidgetManifest;
