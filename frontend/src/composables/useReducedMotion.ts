import { onScopeDispose, ref, type Ref } from 'vue';

let shared: Ref<boolean> | null = null;

/** Reactive prefers-reduced-motion. Components use it to skip JS-driven motion
 * (odometer, conveyor, view transitions); CSS motion is guarded centrally in
 * animations.css. */
export function useReducedMotion(): Ref<boolean> {
  if (shared) return shared;
  const reduced = ref(false);
  if (typeof window !== 'undefined' && 'matchMedia' in window) {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    reduced.value = query.matches;
    const onChange = (e: MediaQueryListEvent) => (reduced.value = e.matches);
    query.addEventListener('change', onChange);
    onScopeDispose(() => query.removeEventListener('change', onChange));
  }
  shared = reduced;
  return reduced;
}
