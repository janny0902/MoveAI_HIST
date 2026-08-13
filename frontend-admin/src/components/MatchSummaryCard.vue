<script setup>
import { computed } from 'vue'

const props = defineProps({
  matching: Object,
  spec: Object,
  selection: Object,
})

const capacity = computed(() => props.spec?.capacity_cbm ?? props.matching?.truck_capacity_cbm)
const free = computed(() => props.matching?.usable_free_cbm ?? props.matching?.estimated_free_cbm)
const fill = computed(() => {
  if (!props.matching) return null
  if (props.selection?.filtered) {
    const cap = Number(capacity.value) || 0
    if (!cap) return null
    return Math.min(100, (Number(props.selection.volumeCbm || 0) / cap) * 100)
  }
  return props.matching.fill_percent ?? props.matching.load_factor_percent ?? null
})
const volume = computed(() =>
  props.selection?.filtered ? props.selection.volumeCbm : props.matching?.selected_volume_cbm ?? props.matching?.total_volume_cbm,
)
const count = computed(() =>
  props.selection?.filtered ? props.selection.cargoCount : props.matching?.selected_cargo_count ?? props.matching?.cargo_count,
)
</script>

<template>
  <section v-if="matching" class="card">
    <h2 class="card-title">적재 요약</h2>
    <div class="summary-grid">
      <div>
        <label>적재함</label>
        <p>{{ capacity != null ? `${Number(capacity).toFixed(2)} CBM` : '-' }}</p>
      </div>
      <div>
        <label>가용</label>
        <p>{{ free != null ? `${Number(free).toFixed(2)} CBM` : '-' }}</p>
      </div>
      <div>
        <label>선택 물량</label>
        <p>{{ volume != null ? `${Number(volume).toFixed(2)} CBM` : '-' }}</p>
      </div>
      <div>
        <label>건수</label>
        <p>{{ count != null ? `${count}건` : '-' }}</p>
      </div>
    </div>
    <div v-if="fill != null" class="fill-row">
      <span>예상 적재율</span>
      <strong>{{ Number(fill).toFixed(1) }}%</strong>
    </div>
    <div class="progress-bar">
      <div class="fill" :style="{ width: Math.min(100, Number(fill || 0)) + '%' }"></div>
    </div>
  </section>
</template>

<style scoped>
.card-title { margin: 0 0 10px; font-size: 15px; font-weight: 800; }
.summary-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px;
}
.summary-grid label { display: block; font-size: 11px; color: var(--muted); }
.summary-grid p { margin: 2px 0 0; font-weight: 800; font-size: 14px; }
.fill-row {
  display: flex; justify-content: space-between; font-size: 13px; font-weight: 700;
}
.progress-bar { height: 8px; background: #eee; border-radius: 4px; margin-top: 8px; overflow: hidden; }
.progress-bar .fill { height: 100%; background: var(--kakao-yellow); }
</style>
