<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { dimsText, fetchTruckList, fetchTruckSpec, modelText, truckOptionText } from '../lib/truck'

const props = defineProps({
  truckId: { type: String, required: true },
  busy: Boolean,
  ranAt: [Date, Object, null],
  candidateLimit: { type: [String, Number], default: '10000' },
  candidateLimitMax: Number,
  candidateLimitUsed: Number,
  palletized: { type: Boolean, default: true },
})
const emit = defineEmits(['update:truckId', 'update:candidateLimit', 'update:palletized', 'run', 'spec'])

const CANDIDATE_OPTIONS = [500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
const trucks = ref([])
const manual = ref(false)
const spec = ref(null)
const specState = ref('idle')

const dims = computed(() => dimsText(spec.value))
const model = computed(() => modelText(spec.value))

const limitOptions = computed(() => {
  const max = props.candidateLimitMax
  if (!max) return CANDIDATE_OPTIONS
  return CANDIDATE_OPTIONS.filter((n) => n <= max)
})

onMounted(async () => {
  try {
    trucks.value = await fetchTruckList()
  } catch {
    manual.value = true
  }
})

watch(
  () => props.truckId,
  (id) => {
    const trimmed = (id || '').trim()
    if (!trimmed) {
      spec.value = null
      specState.value = 'idle'
      emit('spec', null)
      return
    }
    let alive = true
    specState.value = 'loading'
    const timer = setTimeout(async () => {
      try {
        const s = await fetchTruckSpec(trimmed)
        if (!alive) return
        spec.value = s
        specState.value = s ? 'ok' : 'none'
        emit('spec', s)
      } catch {
        if (!alive) return
        spec.value = null
        specState.value = 'error'
        emit('spec', null)
      }
    }, 400)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  },
  { immediate: true },
)
</script>

<template>
  <section class="card">
    <div class="location-head">
      <label class="field-label" for="truckId">차량 번호</label>
      <button v-if="!manual && trucks.length" type="button" class="linkish" @click="manual = true">직접 입력</button>
      <button v-else-if="manual && trucks.length" type="button" class="linkish" @click="manual = false">목록에서 선택</button>
    </div>

    <select
      v-if="!manual && trucks.length"
      id="truckId"
      class="text-input"
      :value="truckId"
      @change="emit('update:truckId', $event.target.value)"
    >
      <option v-for="t in trucks" :key="t.truck_id" :value="t.truck_id">{{ truckOptionText(t) }}</option>
    </select>
    <input
      v-else
      id="truckId"
      class="text-input"
      :value="truckId"
      placeholder="T-000001"
      @input="emit('update:truckId', $event.target.value)"
    />

    <p v-if="specState === 'loading'" class="muted">제원 조회 중…</p>
    <p v-else-if="specState === 'ok' && spec" class="ok-message">
      {{ model || truckId }}
      <template v-if="dims"> · {{ dims }}</template>
      <template v-if="spec.capacity_cbm != null"> · {{ spec.capacity_cbm }} CBM</template>
    </p>
    <p v-else-if="specState === 'none'" class="muted">등록되지 않은 차량입니다.</p>
    <p v-else-if="specState === 'error'" class="dialog-error">제원을 불러오지 못했습니다.</p>

    <label class="field-label" style="margin-top:12px">후보 상한</label>
    <select
      class="text-input"
      :value="candidateLimit"
      @change="emit('update:candidateLimit', $event.target.value)"
    >
      <option v-for="n in limitOptions" :key="n" :value="String(n)">{{ n.toLocaleString() }}건</option>
    </select>
    <p v-if="candidateLimitUsed" class="muted">이번 조회 {{ Number(candidateLimitUsed).toLocaleString() }}건</p>

    <label class="check-row">
      <input
        type="checkbox"
        :checked="palletized"
        @change="emit('update:palletized', $event.target.checked)"
      />
      파렛트 적재 기준
    </label>

    <button type="button" class="btn" :disabled="busy || !truckId" @click="emit('run')">
      {{ busy ? '계산 중…' : '적재 가능 물량 보기' }}
    </button>
    <p v-if="ranAt" class="muted">마지막 실행 {{ new Date(ranAt).toLocaleTimeString('ko-KR') }}</p>
  </section>
</template>

<style scoped>
.check-row {
  display: flex; align-items: center; gap: 8px;
  margin-top: 10px; font-size: 13px; font-weight: 600;
}
.linkish {
  border: none; background: none; color: var(--accent-ink);
  font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit;
}
</style>
