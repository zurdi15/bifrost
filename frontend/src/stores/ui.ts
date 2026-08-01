import { defineStore } from 'pinia';
import { ref } from 'vue';

/** Cross-view UI state: the global edit mode (widgets + drag ordering). */
export const useUiStore = defineStore('ui', () => {
  const editing = ref(false);
  return { editing };
});
