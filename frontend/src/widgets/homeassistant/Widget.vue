<script setup lang="ts">
import { onMounted, onScopeDispose, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import BfNumberRoll from '@/lib/data/BfNumberRoll.vue';
import BfSkeleton from '@/lib/structural/BfSkeleton.vue';

interface HAEntity {
  entity_id: string;
  name: string;
  state: string | null;
  unit: string | null;
}

interface HAData {
  configured: boolean;
  entities: HAEntity[];
}

const props = defineProps<{ widgetId: number; config: Record<string, unknown> }>();

const { t } = useI18n();
const data = ref<HAData | null>(null);
const failed = ref(false);

async function load(): Promise<void> {
  try {
    const response = await fetch(`/api/v1/widgets/${props.widgetId}/data`);
    if (!response.ok) throw new Error(String(response.status));
    data.value = (await response.json()).data;
    failed.value = false;
  } catch {
    failed.value = true;
  }
}

onMounted(load);
const timer = setInterval(load, 60 * 1000);
onScopeDispose(() => clearInterval(timer));

function numeric(state: string | null): number | null {
  if (state === null || state.trim() === '') return null;
  const value = Number(state);
  return Number.isFinite(value) ? value : null;
}
</script>

<template>
  <div class="ha">
    <template v-if="failed">
      <p class="hint">{{ t('widgets.haError') }}</p>
    </template>
    <template v-else-if="data && !data.configured">
      <p class="hint">{{ t('widgets.haNotConfigured') }}</p>
    </template>
    <template v-else-if="data">
      <ul class="entities">
        <li v-for="entity in data.entities" :key="entity.entity_id" class="entity">
          <span class="name" :title="entity.entity_id">{{ entity.name }}</span>
          <span class="value bf-metric">
            <template v-if="entity.state === null">—</template>
            <template v-else-if="numeric(entity.state) !== null">
              <BfNumberRoll :value="numeric(entity.state)!" :decimals="entity.state.includes('.') ? 1 : 0" />
              <span v-if="entity.unit" class="unit">{{ entity.unit }}</span>
            </template>
            <template v-else>
              {{ entity.state }}<span v-if="entity.unit" class="unit"> {{ entity.unit }}</span>
            </template>
          </span>
        </li>
      </ul>
    </template>
    <template v-else>
      <BfSkeleton width="100%" height="0.9rem" />
      <BfSkeleton width="80%" height="0.9rem" />
    </template>
  </div>
</template>

<style scoped>
.ha {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  min-height: 3rem;
  justify-content: center;
}
.hint {
  margin: 0;
  font-size: 0.72rem;
  color: var(--bf-ink-muted);
}
.entities {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.entity {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.6rem;
  min-width: 0;
}
.name {
  font-size: 0.75rem;
  color: var(--bf-ink-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.value {
  flex: none;
  font-size: 0.85rem;
  color: var(--bf-ink);
}
.unit {
  font-size: 0.68rem;
  color: var(--bf-ink-muted);
  margin-left: 0.15rem;
}
</style>
