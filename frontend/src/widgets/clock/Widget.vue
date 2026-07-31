<script setup lang="ts">
import { computed, onScopeDispose, ref } from 'vue';

import BfNumberRoll from '@/lib/data/BfNumberRoll.vue';

const props = defineProps<{ config: Record<string, unknown> }>();

const now = ref(new Date());
const timer = setInterval(() => (now.value = new Date()), 250);
onScopeDispose(() => clearInterval(timer));

const showSeconds = computed(() => props.config.show_seconds !== false);
const hours = computed(() => now.value.getHours());
const minutes = computed(() => now.value.getMinutes());
const seconds = computed(() => now.value.getSeconds());
const dateLabel = computed(() =>
  now.value.toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }),
);
</script>

<template>
  <div class="clock">
    <div class="time" aria-live="off">
      <BfNumberRoll :value="hours" :pad="2" class="unit" />
      <span class="sep">:</span>
      <BfNumberRoll :value="minutes" :pad="2" class="unit" />
      <template v-if="showSeconds">
        <span class="sep">:</span>
        <BfNumberRoll :value="seconds" :pad="2" class="unit seconds" />
      </template>
    </div>
    <p class="date">{{ dateLabel }}</p>
  </div>
</template>

<style scoped>
.clock {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  min-height: 90px;
}
.time {
  display: flex;
  align-items: baseline;
  font-size: 2rem;
  font-weight: 600;
  color: var(--bf-ink-strong);
}
.seconds {
  font-size: 1.3rem;
  color: var(--bf-ink-secondary);
}
.sep {
  color: var(--bf-ink-faint);
  margin: 0 0.12em;
}
.date {
  margin: 0;
  font-size: 0.75rem;
  color: var(--bf-ink-muted);
  text-transform: capitalize;
}
</style>
