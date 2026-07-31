<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { api } from '@/api/client';
import type { FsMount } from '@/api/types';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import BfCapacityBar from '@/lib/data/BfCapacityBar.vue';
import { useLiveStore } from '@/stores/live';
import { formatBytes } from '@/utils/format';

const props = defineProps<{ uuid: string }>();

const { t } = useI18n();
const live = useLiveStore();

const mounts = ref<FsMount[]>([]);

onMounted(async () => {
  try {
    mounts.value = await api.nodeFs(props.uuid);
  } catch {
    /* node without fs data yet */
  }
});

const liveMounts = computed(() => live.fs.get(props.uuid));
watch(liveMounts, (next) => {
  if (next) mounts.value = next;
});
</script>

<template>
  <section v-if="mounts.length > 0" class="filesystems">
    <h2 class="title">{{ t('detail.filesystems') }}</h2>
    <BfCard class="list" :padded="false">
      <div v-for="(mount, i) in mounts" :key="mount.mountpoint" class="row">
        <div class="line">
          <span class="mountpoint bf-metric">{{ mount.mountpoint }}</span>
          <BfChip v-if="mount.fstype" tone="neutral">{{ mount.fstype }}</BfChip>
          <BfChip v-if="mount.stale" tone="warn">{{ t('detail.stale') }}</BfChip>
          <span v-if="!mount.stale" class="usage bf-metric">
            {{ formatBytes(mount.used_bytes ?? 0) }} / {{ formatBytes(mount.total_bytes ?? 0) }}
            <strong>{{ mount.used_pct?.toFixed(0) }}%</strong>
          </span>
        </div>
        <BfCapacityBar v-if="!mount.stale" :value="mount.used_pct ?? 0" :index="i" />
      </div>
    </BfCard>
  </section>
</template>

<style scoped>
.filesystems {
  margin-top: 2rem;
}
.title {
  margin: 0 0 1rem;
  font-size: 0.85rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--bf-ink-secondary);
}
.list {
  display: flex;
  flex-direction: column;
}
.row {
  padding: 0.8rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.row + .row {
  border-top: 1px solid var(--bf-line);
}
.line {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.mountpoint {
  font-size: 0.82rem;
  color: var(--bf-ink-strong);
  font-weight: 600;
}
.usage {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--bf-ink-secondary);
}
.usage strong {
  color: var(--bf-ink-strong);
  margin-left: 0.4em;
}
</style>
