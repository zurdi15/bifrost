import { createRouter, createWebHistory } from "vue-router";
import { nextTick } from "vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "dashboard",
      component: () => import("@/views/DashboardView.vue"),
    },
    {
      path: "/nodes",
      name: "nodes",
      component: () => import("@/views/NodesView.vue"),
    },
    {
      path: "/nodes/:uuid",
      name: "node-detail",
      component: () => import("@/views/NodeDetailView.vue"),
    },
    {
      path: "/storage",
      name: "storage",
      component: () => import("@/views/StorageView.vue"),
    },
    {
      path: "/jobs",
      name: "jobs",
      component: () => import("@/views/JobsView.vue"),
    },
    {
      path: "/gateway",
      name: "gateway",
      component: () => import("@/views/GatewayView.vue"),
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("@/views/SettingsView.vue"),
    },
  ],
});

// Hero morph: shared view-transition-name on NodeCard and the detail hero
// turns navigation into an element morph. Feature-detected; the bf-view
// <Transition> in App.vue is the fallback, and reduced-motion skips both.
router.beforeResolve(() => {
  if (
    typeof document === "undefined" ||
    !("startViewTransition" in document) ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ) {
    return;
  }
  return new Promise<void>((resolve) => {
    (
      document as Document & {
        startViewTransition: (cb: () => Promise<void>) => void;
      }
    ).startViewTransition(() => {
      resolve();
      return nextTick();
    });
  });
});

export default router;
