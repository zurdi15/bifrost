<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import SortableList from '@/components/SortableList.vue';
import BfChip from '@/lib/primitives/BfChip.vue';
import BfCard from '@/lib/structural/BfCard.vue';
import BfStatusDot from '@/lib/data/BfStatusDot.vue';
import { useLayoutStore } from '@/stores/layout';
import { useLiveStore } from '@/stores/live';
import { formatClock } from '@/utils/format';

interface Cluster {
  id: number;
  name: string;
  source: string;
  status: string | null;
  enabled: boolean;
  has_credentials: boolean;
}

interface CronJob {
  id: number;
  cluster_id: number;
  namespace: string;
  name: string;
  schedule: string | null;
  suspended: boolean;
  last_run_ts: number | null;
  last_result: string | null;
  last_duration_s: number | null;
}

interface JobRun {
  job_name: string;
  finished_ts: number | null;
  succeeded: boolean | null;
  duration_s: number | null;
  failure_reason: string | null;
}

const { t } = useI18n();
const live = useLiveStore();
const layout = useLayoutStore();

const clusters = ref<Cluster[]>([]);
const cronjobs = ref<CronJob[]>([]);
const cronjobId = (cronjob: CronJob): string => String(cronjob.id);
const orderedCronjobs = computed(() => layout.apply('jobs', cronjobs.value, cronjobId));
const runsByCronjob = ref(new Map<number, JobRun[]>());
const loaded = ref(false);

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`);
  if (!response.ok) throw new Error(`${path} → ${response.status}`);
  return response.json();
}

async function load(): Promise<void> {
  try {
    [clusters.value, cronjobs.value] = await Promise.all([
      getJson<Cluster[]>('/k8s/clusters'),
      getJson<CronJob[]>('/k8s/cronjobs'),
    ]);
    const runs = await Promise.all(
      cronjobs.value.map(async (cronjob): Promise<[number, JobRun[]]> => {
        try {
          return [cronjob.id, await getJson<JobRun[]>(`/k8s/cronjobs/${cronjob.id}/runs`)];
        } catch {
          return [cronjob.id, []];
        }
      }),
    );
    runsByCronjob.value = new Map(runs);
  } finally {
    loaded.value = true;
  }
}

onMounted(load);
watch(() => live.k8sVersion, load);

function cronjobStatus(cronjob: CronJob): string {
  if (cronjob.suspended) return 'disabled';
  if (cronjob.last_result === 'failed') return 'offline';
  if (cronjob.last_result === 'ok') return 'online';
  return 'new';
}

function clusterTone(cluster: Cluster): 'up' | 'warn' | 'down' | 'unknown' {
  if (!cluster.enabled) return 'unknown';
  if (cluster.status === 'ok') return 'up';
  if (cluster.status?.startsWith('error')) return 'down';
  return 'warn';
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}
</script>

<template>
  <section>
    <header class="section-head">
      <h2 class="title">{{ t('jobs.title') }}</h2>
      <span class="clusters">
        <BfChip v-for="cluster in clusters" :key="cluster.id" :tone="clusterTone(cluster)" mono>
          {{ cluster.name }}
          <template v-if="!cluster.has_credentials"> · {{ t('jobs.needsCreds') }}</template>
        </BfChip>
      </span>
    </header>

    <p v-if="loaded && clusters.length === 0" class="empty">{{ t('jobs.noClusters') }}</p>
    <p v-else-if="loaded && cronjobs.length === 0" class="empty">{{ t('jobs.noCronjobs') }}</p>

    <SortableList
      class="list bf-stagger"
      :items="orderedCronjobs"
      :id-of="cronjobId"
      @reorder="(ids) => layout.setOrder('jobs', ids)"
    >
      <template #item="{ element: cronjob, index: i }">
      <BfCard
        :padded="false"
        class="job"
        :style="{ '--i': i }"
      >
        <details>
          <summary class="row">
            <BfStatusDot
              :status="cronjobStatus(cronjob)"
              :desync-id="`cj-${cronjob.id}`"
              :size="8"
            />
            <span class="name">{{ cronjob.name }}</span>
            <BfChip tone="neutral">{{ cronjob.namespace }}</BfChip>
            <span v-if="cronjob.schedule" class="schedule bf-metric">{{ cronjob.schedule }}</span>
            <span class="spacer" />
            <!-- Recent-run strip: newest right, state always icon+color pair. -->
            <span class="strip" aria-hidden="true">
              <span
                v-for="run in (runsByCronjob.get(cronjob.id) ?? []).slice(0, 14).reverse()"
                :key="run.job_name"
                class="tick"
                :class="run.succeeded ? 'ok' : 'fail'"
              />
            </span>
            <BfChip
              v-if="cronjob.last_result"
              :tone="cronjob.last_result === 'ok' ? 'up' : 'down'"
              mono
            >
              {{ cronjob.last_result }}
              <template v-if="cronjob.last_run_ts">
                · {{ formatClock(cronjob.last_run_ts) }}
              </template>
              · {{ formatDuration(cronjob.last_duration_s) }}
            </BfChip>
            <BfChip v-else tone="unknown">{{ t('jobs.noRuns') }}</BfChip>
          </summary>

          <ul class="runs bf-metric">
            <li v-for="run in runsByCronjob.get(cronjob.id) ?? []" :key="run.job_name" class="run">
              <span class="tick" :class="run.succeeded ? 'ok' : 'fail'" />
              <span class="run-name">{{ run.job_name }}</span>
              <span v-if="run.finished_ts">{{ formatClock(run.finished_ts) }}</span>
              <span>{{ formatDuration(run.duration_s) }}</span>
              <span v-if="run.failure_reason" class="reason">{{ run.failure_reason }}</span>
            </li>
            <li v-if="(runsByCronjob.get(cronjob.id) ?? []).length === 0" class="run">
              {{ t('jobs.noRuns') }}
            </li>
          </ul>
        </details>
      </BfCard>
      </template>
    </SortableList>
  </section>
</template>

<style scoped>
.section-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0 1.1rem;
  flex-wrap: wrap;
}
.title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--bf-ink-secondary);
}
.clusters {
  display: flex;
  gap: 0.4rem;
  margin-left: auto;
  flex-wrap: wrap;
}
.empty {
  color: var(--bf-ink-muted);
  padding: 2.5rem 0;
  text-align: center;
}
.list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.7rem 1rem;
  cursor: pointer;
  list-style: none;
  flex-wrap: wrap;
}
.row::-webkit-details-marker {
  display: none;
}
.name {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--bf-ink-strong);
}
.schedule {
  font-size: 0.72rem;
  color: var(--bf-ink-muted);
}
.spacer {
  flex: 1;
}
.strip {
  display: inline-flex;
  gap: 3px;
  align-items: center;
}
.tick {
  width: 7px;
  height: 14px;
  border-radius: 2px;
  display: inline-block;
  flex: none;
}
.tick.ok {
  background: var(--bf-status-up);
  opacity: 0.75;
}
.tick.fail {
  background: var(--bf-status-down);
}
.runs {
  margin: 0;
  padding: 0.3rem 1rem 0.8rem;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  animation: bf-rise-in var(--bf-dur-300) var(--bf-ease-spring) both;
}
.run {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  font-size: 0.74rem;
  color: var(--bf-ink-secondary);
}
.run .tick {
  height: 10px;
  width: 5px;
}
.run-name {
  color: var(--bf-ink);
}
.reason {
  color: var(--bf-status-down);
}
</style>
