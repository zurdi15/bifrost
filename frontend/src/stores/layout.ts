import { defineStore } from 'pinia';
import { reactive, ref } from 'vue';

export interface AmbientEntry {
  id: number;
  size: string;
}

/** Single owner of the persisted dashboard layout (/api/v1/dashboard):
 * the ambient widget arrangement plus per-list drag orders. Centralized so
 * no writer clobbers another's slice of the JSON. */
export const useLayoutStore = defineStore('layout', () => {
  const loaded = ref(false);
  const ambient = ref<AmbientEntry[]>([]);
  const orders = reactive(new Map<string, string[]>());
  let loadPromise: Promise<void> | null = null;

  function load(): Promise<void> {
    loadPromise ??= (async () => {
      try {
        const response = await fetch('/api/v1/dashboard');
        if (!response.ok) throw new Error(String(response.status));
        const layout = await response.json();
        ambient.value = (layout.ambient as AmbientEntry[]) ?? [];
        for (const [key, ids] of Object.entries(layout.orders ?? {})) {
          orders.set(key, ids as string[]);
        }
      } catch {
        /* fresh hub or offline: defaults apply */
      } finally {
        loaded.value = true;
      }
    })();
    return loadPromise;
  }

  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  function save(): void {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      void fetch('/api/v1/dashboard', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ambient: ambient.value,
          orders: Object.fromEntries(orders),
        }),
      });
    }, 600);
  }

  function setOrder(key: string, ids: string[]): void {
    orders.set(key, ids);
    save();
  }

  /** Sort by the saved order; unknown ids keep their natural order at the
   * end (new nodes/services appear where they always did until dragged). */
  function apply<T>(key: string, items: T[], idOf: (item: T) => string): T[] {
    const order = orders.get(key);
    if (!order || order.length === 0) return items;
    const rank = new Map(order.map((id, index) => [id, index]));
    return [...items].sort(
      (a, b) =>
        (rank.get(idOf(a)) ?? order.length) - (rank.get(idOf(b)) ?? order.length),
    );
  }

  return { loaded, ambient, orders, load, save, setOrder, apply };
});
