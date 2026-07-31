import type { Component } from 'vue';

export type WidgetSize = '1x1' | '2x1';

export interface WidgetManifest {
  /** Matches the hub-side type_id. */
  id: string;
  titleKey: string;
  sizes: WidgetSize[];
  defaultSize: WidgetSize;
  defaultConfig: Record<string, unknown>;
  /** Widget needs /widgets/{id}/data from the hub (weather); clock doesn't. */
  fetchesData: boolean;
  component: () => Promise<Component>;
  configComponent?: () => Promise<Component>;
}

/** Contributing a widget = adding a folder with a manifest.ts next to this
 * file; the glob picks it up, nothing in the core changes. */
const modules = import.meta.glob<{ default: WidgetManifest }>('./*/manifest.ts', {
  eager: true,
});

export const WIDGETS: Record<string, WidgetManifest> = Object.fromEntries(
  Object.values(modules).map((m) => [m.default.id, m.default]),
);
