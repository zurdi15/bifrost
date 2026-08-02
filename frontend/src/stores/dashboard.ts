import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";

/** How the service cards bucket together. A per-browser view preference. */
export const GROUP_MODES = [
  { id: "group", label: "services.byGroup" },
  { id: "node", label: "services.byNode" },
  { id: "state", label: "services.byState" },
] as const;
export type GroupMode = (typeof GROUP_MODES)[number]["id"];

/**
 * Dashboard toolbar state — owned by the toolbar in DashboardView and read
 * by the tab sections that filter with it. Lives outside the sections so
 * switching tabs never remounts or resets it (the search survives the swap).
 */
export const useDashboardStore = defineStore("dashboard", () => {
  const stored = localStorage.getItem(
    "bf-services-groupby",
  ) as GroupMode | null;
  const groupMode = ref<GroupMode>(
    GROUP_MODES.some((mode) => mode.id === stored) ? stored! : "group",
  );
  watch(groupMode, (mode) => localStorage.setItem("bf-services-groupby", mode));

  const nodeFilter = ref<string | null>(null);
  const showHidden = ref(false);

  const query = ref("");
  const needle = computed(() => query.value.trim().toLowerCase());

  return { groupMode, nodeFilter, showHidden, query, needle };
});
