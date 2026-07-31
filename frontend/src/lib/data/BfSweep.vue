<script setup lang="ts">
/**
 * One-shot perimeter light sweep overlaid on a rounded parent (position:
 * relative required). 'down' announces a node loss; 'aurora' celebrates
 * recovery. Parent toggles `active` (re-add per event).
 */
withDefaults(
  defineProps<{
    tone?: 'down' | 'aurora';
    active?: boolean;
  }>(),
  { tone: 'down', active: false },
);
</script>

<template>
  <span v-if="active" class="bf-sweep" :class="tone" aria-hidden="true" />
</template>

<style scoped>
.bf-sweep {
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  padding: 1.5px;
  pointer-events: none;
  -webkit-mask:
    linear-gradient(black 0 0) content-box,
    linear-gradient(black 0 0);
  -webkit-mask-composite: xor;
  mask:
    linear-gradient(black 0 0) content-box,
    linear-gradient(black 0 0);
  mask-composite: exclude;
  animation: bf-sweep 900ms ease-out both;
}
.down {
  background: conic-gradient(
    from var(--bf-sweep-a),
    var(--bf-status-down),
    transparent 130deg
  );
}
.aurora {
  background: conic-gradient(
    from var(--bf-sweep-a),
    var(--bf-aurora-1),
    var(--bf-aurora-3),
    var(--bf-aurora-5),
    transparent 160deg
  );
}
</style>
