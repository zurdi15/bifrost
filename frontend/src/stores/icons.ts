import { defineStore } from 'pinia';
import { reactive } from 'vue';

import { api } from '@/api/client';
import { iconCandidates } from '@/utils/autoIcon';

interface IconSubject {
  name: string;
  image: string | null;
}

/** Auto-icon resolution: cards call ensure() for services without an icon;
 * lookups batch into one /icons request and results land in a reactive map
 * (null = known miss, absent = not asked yet, so transient failures retry). */
export const useIconStore = defineStore('icons', () => {
  const resolved = reactive(new Map<string, string | null>());
  const queue = new Set<string>();
  let timer: ReturnType<typeof setTimeout> | null = null;

  async function flush(): Promise<void> {
    timer = null;
    const names = [...queue];
    queue.clear();
    if (names.length === 0) return;
    try {
      const got = await api.resolveIcons(names);
      for (const name of names) resolved.set(name, got[name] ?? null);
    } catch {
      // Leave them unset: the next ensure() retries.
    }
  }

  function ensure(subject: IconSubject): void {
    for (const name of iconCandidates(subject)) {
      if (!resolved.has(name)) queue.add(name);
    }
    if (queue.size > 0 && timer === null) timer = setTimeout(() => void flush(), 50);
  }

  function iconFor(subject: IconSubject): string | null {
    for (const name of iconCandidates(subject)) {
      const hit = resolved.get(name);
      if (hit) return hit;
    }
    return null;
  }

  return { resolved, ensure, iconFor, flush };
});
