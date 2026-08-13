<script setup>
import { computed, ref } from 'vue'
import { loadPref, savePref } from './lib/prefs'
import { resetDemoData } from './lib/waybill'
import { useTruckMatch } from './composables/useTruckMatch'
import TruckMatchCard from './components/TruckMatchCard.vue'
import MatchSummaryCard from './components/MatchSummaryCard.vue'
import TerminalGroupList from './components/TerminalGroupList.vue'
import CargoRegisterScreen from './components/CargoRegisterScreen.vue'
import CargoListScreen from './components/CargoListScreen.vue'

const TABS = [
  { key: 'capture', label: '관리자 · 적재 배정' },
  { key: 'cargo', label: '화주사 · 등록' },
  { key: 'list', label: '대기 운송장' },
]

const tab = ref('capture')
const truckId = ref(loadPref('truckId', 'T-000001'))
const gps = ref(null)
const override = ref(null)
const spec = ref(null)
const originFilter = ref([])
const destFilter = ref([])
const candidateLimit = ref('10000')
const palletized = ref(true)
const demoBusy = ref(false)
const demoMsg = ref(null)

const { matching, busy, error, ranAt, run, reset } = useTruckMatch()

const basePosition = computed(() => override.value?.position || gps.value?.position || null)

const allGroups = computed(() => matching.value?.terminal_groups || [])
const visibleGroups = computed(() =>
  allGroups.value.filter(
    (g) =>
      (originFilter.value.length === 0 || originFilter.value.includes(g.origin_terminal_code)) &&
      (destFilter.value.length === 0 || destFilter.value.includes(g.destination_terminal_code)),
  ),
)
const selection = computed(() => ({
  filtered: originFilter.value.length > 0 || destFilter.value.length > 0,
  volumeCbm: visibleGroups.value.reduce((s, g) => s + (g.volume_cbm || 0), 0),
  cargoCount: visibleGroups.value.reduce((s, g) => s + (g.cargo_count || 0), 0),
  weightKg: visibleGroups.value.reduce((s, g) => s + (g.weight_kg || 0), 0),
}))

function changeTruckId(id) {
  truckId.value = id
  savePref('truckId', id)
  reset()
  originFilter.value = []
  destFilter.value = []
}

function runMatch() {
  return run(truckId.value, basePosition.value, candidateLimit.value || undefined, palletized.value)
}

async function onDemoReset() {
  if (demoBusy.value) return
  if (!window.confirm('시연 데이터를 초기 상태로 되돌릴까요?')) return
  demoBusy.value = true
  demoMsg.value = null
  try {
    const data = await resetDemoData()
    reset()
    demoMsg.value = data.message || `초기화 완료 · 그룹 ${data.groupsCreated ?? '-'}개`
  } catch (err) {
    demoMsg.value = err.message || String(err)
  } finally {
    demoBusy.value = false
  }
}

function onUseGps() {
  override.value = null
}

async function locateMe() {
  if (!navigator.geolocation) {
    demoMsg.value = '이 브라우저는 위치를 지원하지 않습니다.'
    return
  }
  navigator.geolocation.getCurrentPosition(
    (p) => {
      gps.value = { position: { lat: p.coords.latitude, lng: p.coords.longitude } }
    },
    (err) => {
      demoMsg.value = err.message || '위치를 가져오지 못했습니다.'
    },
    { enableHighAccuracy: true, timeout: 12000 },
  )
}
</script>

<template>
  <header class="k-header">
    <div class="k-header-inner">
      <span class="brand">moveAI</span>
      <span class="brand-tag">관리자 · Vue</span>
      <button type="button" class="driver-link" @click="location.href = '/'">기사 화면</button>
      <button
        type="button"
        class="driver-link demo-reset-btn"
        :disabled="demoBusy"
        @click="onDemoReset"
      >
        {{ demoBusy ? '초기화 중…' : '시연 리셋' }}
      </button>
    </div>
  </header>

  <main class="app">
    <h1>화물칸 공간 분석</h1>
    <p v-if="demoMsg" :class="demoMsg.includes('실패') ? 'dialog-error' : 'ok-message'">{{ demoMsg }}</p>

    <nav class="tabs" role="tablist">
      <button
        v-for="t in TABS"
        :key="t.key"
        type="button"
        role="tab"
        class="tab"
        :class="{ active: tab === t.key }"
        :aria-selected="tab === t.key"
        @click="tab = t.key"
      >
        {{ t.label }}
      </button>
    </nav>

    <template v-if="tab === 'list'">
      <p class="sub">적재된 대기 운송장과 상차 터미널을 확인합니다.</p>
      <CargoListScreen />
    </template>

    <template v-else-if="tab === 'cargo'">
      <p class="sub">체적이 측정된 운송장을 위치와 함께 등록합니다.</p>
      <CargoRegisterScreen />
    </template>

    <template v-else>
      <p class="sub">
        배차된 차를 고르고 버튼을 누르면 지금 실을 수 있는 물량과 적재율을 보여줍니다.
        적재함은 빈 차(0%) 기준으로 계산합니다.
      </p>

      <section class="card">
        <div class="location-head">
          <span class="field-label">기준 위치</span>
          <button type="button" class="linkish" @click="locateMe">GPS 가져오기</button>
        </div>
        <p v-if="basePosition" class="muted">
          {{ override?.label || '현재 위치' }}
          · {{ basePosition.lat.toFixed(5) }}, {{ basePosition.lng.toFixed(5) }}
        </p>
        <p v-else class="muted">위치가 없습니다. GPS를 허용하거나 매칭은 서버 저장 좌표로 진행됩니다.</p>
        <button v-if="override" type="button" class="btn secondary" @click="onUseGps">GPS로 되돌리기</button>
      </section>

      <TruckMatchCard
        :truck-id="truckId"
        :busy="busy"
        :ran-at="ranAt"
        :candidate-limit="candidateLimit"
        :candidate-limit-max="matching?.candidate_limit_max"
        :candidate-limit-used="matching?.candidate_limit"
        :palletized="palletized"
        @update:truck-id="changeTruckId"
        @update:candidate-limit="candidateLimit = $event"
        @update:palletized="palletized = $event"
        @run="runMatch"
        @spec="spec = $event"
      />

      <section v-if="error" class="card error" role="alert">{{ error }}</section>

      <section v-if="matching && !matching.can_load" class="card notice">
        지금 실을 수 있는 운송장이 없습니다.
        <span v-if="matching.failure_reason" class="muted"> · 사유 {{ matching.failure_reason }}</span>
      </section>

      <MatchSummaryCard :matching="matching" :spec="spec" :selection="selection" />

      <TerminalGroupList
        :groups="visibleGroups"
        :all-groups="allGroups"
        :origin-filter="originFilter"
        :dest-filter="destFilter"
        @update:origin-filter="originFilter = $event"
        @update:dest-filter="destFilter = $event"
        @clear="originFilter = []; destFilter = []"
      />
    </template>
  </main>
</template>
