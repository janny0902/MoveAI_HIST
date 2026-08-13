<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 180000 })

const gate = ref('login') // login | profile | route | app
const tab = ref('cargo') // cargo | drive | ledger
const busy = ref(false)
const message = ref('')
const session = reactive({
  truckId: null,
  driverName: '',
  phone: '',
  truckNumber: '',
  capacityTons: 11,
  capacityM3: 50,
  vehicleType: '윙바디',
  originCode: '200',
  destinationCode: '001',
  remainingVolumePercent: 100,
})

const stations = ref([])
const feed = ref([])
const ledger = ref({ entries: [], netProfit: 0, totalIncome: 0, totalExpense: 0, dailyEsgKg: 0 })
const health = reactive({ spring: '', ai: '' })

const occupied = computed(() => Math.max(0, 100 - (session.remainingVolumePercent || 0)))

function saveSession() {
  sessionStorage.setItem('moveai_session', JSON.stringify(session))
}

function loadSession() {
  try {
    const raw = sessionStorage.getItem('moveai_session')
    if (!raw) return
    Object.assign(session, JSON.parse(raw))
    if (session.truckId) gate.value = 'app'
  } catch (_) { /* ignore */ }
}

async function refreshHealth() {
  try {
    const s = await axios.get('/api/health')
    health.spring = typeof s.data === 'string' ? s.data : 'ok'
  } catch (e) {
    health.spring = 'down'
  }
  try {
    const a = await axios.get('/ai/health')
    health.ai = a.data?.status || 'ok'
  } catch (e) {
    health.ai = 'down'
  }
}

async function login() {
  busy.value = true
  message.value = ''
  try {
    const { data } = await api.post('/drivers/login', {
      phone: session.phone,
      truckNumber: session.truckNumber,
      driverName: session.driverName || undefined,
    })
    applyTruck(data)
    saveSession()
    if (data.needProfile) gate.value = 'profile'
    else if (data.needRoute) gate.value = 'route'
    else gate.value = 'app'
    message.value = data.message || '로그인 완료'
  } catch (e) {
    message.value = e?.response?.data?.message || e.message
  } finally {
    busy.value = false
  }
}

async function saveProfile() {
  busy.value = true
  try {
    const { data } = await api.post(`/drivers/${session.truckId}/profile`, {
      driverName: session.driverName,
      capacityTons: session.capacityTons,
      capacityM3: session.capacityM3,
      vehicleType: session.vehicleType,
      remainingVolumePercent: session.remainingVolumePercent,
    })
    applyTruck(data)
    saveSession()
    gate.value = data.needRoute ? 'route' : 'app'
  } catch (e) {
    message.value = e.message
  } finally {
    busy.value = false
  }
}

async function saveRoute() {
  busy.value = true
  try {
    const { data } = await api.post(`/drivers/${session.truckId}/route`, {
      originCode: session.originCode,
      destinationCode: session.destinationCode,
    })
    applyTruck(data)
    saveSession()
    gate.value = 'app'
  } catch (e) {
    message.value = e.message
  } finally {
    busy.value = false
  }
}

function applyTruck(data) {
  session.truckId = data.truckId
  session.driverName = data.driverName || session.driverName
  session.phone = data.phone || session.phone
  session.truckNumber = data.truckNumber || session.truckNumber
  session.capacityTons = data.capacityTons ?? session.capacityTons
  session.capacityM3 = data.capacityM3 ?? session.capacityM3
  session.vehicleType = data.vehicleType || session.vehicleType
  session.originCode = data.originCode || session.originCode
  session.destinationCode = data.destinationCode || session.destinationCode
  session.remainingVolumePercent = data.remainingVolumePercent ?? 100
}

async function loadStations() {
  const { data } = await api.get('/dispatch/stations')
  stations.value = data.stations || []
}

async function loadFeed() {
  if (!session.truckId) return
  const { data } = await api.get('/dispatch/cargo-feed', { params: { truckId: session.truckId } })
  feed.value = data.items || []
  session.remainingVolumePercent = data.remainingVolumePercent ?? session.remainingVolumePercent
  saveSession()
}

async function loadLedger() {
  if (!session.truckId) return
  const { data } = await api.get('/dispatch/ledger', { params: { truckId: session.truckId } })
  ledger.value = data
}

async function onUpload(ev) {
  const file = ev.target.files?.[0]
  if (!file || !session.truckId) return
  busy.value = true
  message.value = '공간 분석 중...'
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('truckId', String(session.truckId))
    const { data } = await api.post('/load/upload', form)
    session.remainingVolumePercent = data.remainingVolumePercent
    saveSession()
    message.value = (data.logs || []).join(' · ') || data.guide || '분석 완료'
  } catch (e) {
    message.value = e.message
  } finally {
    busy.value = false
    ev.target.value = ''
  }
}

onMounted(async () => {
  loadSession()
  await refreshHealth()
  await loadStations().catch(() => {})
  if (gate.value === 'app') {
    await loadFeed().catch(() => {})
    await loadLedger().catch(() => {})
  }
})
</script>

<template>
  <div class="shell">
    <header class="top">
      <div>
        <strong>moveAI</strong>
        <span class="muted"> · 초기 구축</span>
      </div>
      <div class="muted">API {{ health.spring || '…' }} / AI {{ health.ai || '…' }}</div>
    </header>

    <main v-if="gate === 'login'" class="panel stack gate">
      <h1>기사 로그인</h1>
      <p class="muted">전화 + 트럭번호로 세션을 만듭니다.</p>
      <input v-model="session.phone" placeholder="전화번호 (예: 01012345678)" />
      <input v-model="session.truckNumber" placeholder="트럭번호 (예: TEST100)" />
      <input v-model="session.driverName" placeholder="기사명 (선택)" />
      <button :disabled="busy || !session.phone || !session.truckNumber" @click="login">로그인</button>
      <p v-if="message" class="muted">{{ message }}</p>
    </main>

    <main v-else-if="gate === 'profile'" class="panel stack gate">
      <h1>차량 프로필</h1>
      <input v-model="session.driverName" placeholder="기사명" />
      <input v-model.number="session.capacityTons" type="number" placeholder="톤수" />
      <input v-model.number="session.capacityM3" type="number" placeholder="m³" />
      <input v-model="session.vehicleType" placeholder="차종" />
      <button :disabled="busy" @click="saveProfile">저장</button>
    </main>

    <main v-else-if="gate === 'route'" class="panel stack gate">
      <h1>출도착 터미널</h1>
      <label class="muted">출발</label>
      <select v-model="session.originCode">
        <option v-for="s in stations" :key="'o'+s.code" :value="s.code">{{ s.code }} · {{ s.name }}</option>
      </select>
      <label class="muted">도착</label>
      <select v-model="session.destinationCode">
        <option v-for="s in stations" :key="'d'+s.code" :value="s.code">{{ s.code }} · {{ s.name }}</option>
      </select>
      <button :disabled="busy" @click="saveRoute">운행 시작 준비</button>
    </main>

    <main v-else class="app">
      <section v-show="tab === 'cargo'" class="panel stack">
        <h2>배차목록</h2>
        <p class="muted">트럭 #{{ session.truckId }} · 잔여 {{ session.remainingVolumePercent?.toFixed?.(1) ?? session.remainingVolumePercent }}%</p>
        <p v-if="!feed.length" class="muted">제안 물량 없음 (배차 propose는 다음 단계에서 연결)</p>
        <ul>
          <li v-for="item in feed" :key="item.requestId">{{ item.origin }} → {{ item.destination }}</li>
        </ul>
      </section>

      <section v-show="tab === 'drive'" class="panel stack">
        <h2>운행</h2>
        <p class="muted">{{ session.originCode }} → {{ session.destinationCode }} · 적재 {{ occupied.toFixed(1) }}%</p>
        <label class="upload">
          상차 사진 업로드
          <input type="file" accept="image/*" @change="onUpload" />
        </label>
        <p v-if="message" class="muted">{{ message }}</p>
      </section>

      <section v-show="tab === 'ledger'" class="panel stack">
        <h2>정산</h2>
        <p>순이익 {{ ledger.netProfit?.toLocaleString?.() ?? 0 }}원 · ESG {{ ledger.dailyEsgKg || 0 }}kg</p>
        <p v-if="!(ledger.entries || []).length" class="muted">정산 이력 없음</p>
      </section>

      <nav class="tabs">
        <button :class="{ on: tab === 'cargo' }" @click="tab = 'cargo'; loadFeed()">배차목록</button>
        <button :class="{ on: tab === 'drive' }" @click="tab = 'drive'">운행</button>
        <button :class="{ on: tab === 'ledger' }" @click="tab = 'ledger'; loadLedger()">정산</button>
      </nav>
    </main>
  </div>
</template>

<style scoped>
.shell { min-height: 100vh; display: grid; grid-template-rows: auto 1fr; }
.top {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0.9rem 1rem; border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, #152029, #0f1720);
}
.gate { margin: 2rem auto; width: min(420px, calc(100% - 2rem)); }
.app { padding: 1rem 1rem 5.5rem; }
.tabs {
  position: fixed; left: 0; right: 0; bottom: 0;
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem;
  padding: 0.75rem; background: rgba(15, 23, 32, 0.96);
  border-top: 1px solid var(--line);
}
.tabs button { background: #243140; }
.tabs button.on { background: var(--accent); }
.upload {
  display: grid; gap: 0.4rem; padding: 0.8rem; border: 1px dashed var(--line); border-radius: 12px;
}
.upload input { border: 0; padding: 0; background: transparent; }
h1, h2 { margin: 0; }
</style>
