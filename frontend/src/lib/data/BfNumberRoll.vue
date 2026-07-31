<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';

import { useReducedMotion } from '@/composables/useReducedMotion';

const props = withDefaults(
  defineProps<{
    value: number;
    decimals?: number;
    suffix?: string;
    /** Zero-pad the integer part to this many characters (clocks). */
    pad?: number;
  }>(),
  { decimals: 0, suffix: '', pad: 0 },
);

const reduced = useReducedMotion();

// Mount plays a count-up from 0 by rendering 0 first, then the real value on
// the next frame so every digit column rolls into place.
const displayed = ref(reduced.value ? props.value : 0);
onMounted(() => {
  requestAnimationFrame(() => (displayed.value = props.value));
});
watch(
  () => props.value,
  (v) => (displayed.value = v),
);

function format(value: number): string {
  const text = value.toFixed(props.decimals);
  return props.pad > 0 ? text.padStart(props.pad, '0') : text;
}

const chars = computed(() => format(displayed.value).split(''));
const label = computed(() => `${format(props.value)}${props.suffix}`);
</script>

<template>
  <span class="bf-roll bf-metric" :aria-label="label" role="text">
    <template v-for="(char, i) in chars" :key="chars.length - i">
      <span v-if="/\d/.test(char)" class="digit" aria-hidden="true">
        <span class="col" :style="{ transform: `translateY(-${Number(char)}em)` }">
          <span v-for="n in 10" :key="n">{{ n - 1 }}</span>
        </span>
      </span>
      <span v-else aria-hidden="true">{{ char }}</span>
    </template>
    <span v-if="suffix" class="suffix" aria-hidden="true">{{ suffix }}</span>
  </span>
</template>

<style scoped>
.bf-roll {
  display: inline-flex;
  line-height: 1;
}
.digit {
  display: inline-block;
  height: 1em;
  overflow: hidden;
}
.col {
  display: inline-flex;
  flex-direction: column;
  transition: transform var(--bf-dur-300) var(--bf-ease-spring);
  will-change: transform;
}
.col > span {
  display: block;
  height: 1em;
}
.suffix {
  color: var(--bf-ink-muted);
  margin-left: 0.12em;
}
</style>
