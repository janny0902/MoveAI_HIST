<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 180000 })

const gate = ref('login') // login | profile | route | app
const tab = ref('cargo') // cargo | drive | ledger
const busy = reactive({ show: false, title: '', hint: '', percent: 0 })
const toast = ref(null)
const message = ref('')
const showLogs = ref(false)
const logs = ref([])

const loginForm = reactive({ truckNumber: '', phone: '', driverName: '' })
const profileForm = reactive({
  driverName: '',
  capacityTons: 11,
  capacityM3: 50,
  vehicleType: '윙바디',
  remainingVolumePercent: 100,
})
const routeForm = reactive({ originCode: '200', destinationCode: '001' })

const me = reactive({
  truckId: null,
  driverName: '',
  phone: '',
  truckNumber: '',
  capacityTons: 11,
  capacityM3: 50,
  vehicleType: '윙바디',
  originCode: '',
  originName: '',
  destinationCode: '',
  destinationName: '',
  remainingVolumePercent: 100,
  status: 'IDLE',
})

const stations = ref([])
const feed = ref([])
const ledger = ref({ entries: [], netProfit: 0, totalIncome: 0, totalExpense: 0, dailyEsgKg: 0, entryCount: 0 })
const uploadGuide = ref('')
const fileInput = ref(null)

const occupied = computed(() => Math.max(0, 100 - Number(me.remainingVolumePercent || 0)))
const plannedOccupiedDisplay = computed(() => occupied.value.toFixed(1))

function formatWon(v) {
  const n = Number(v || 0)
  return `${n.toLocaleString('ko-KR')}원`
}

function pushLog(line) {
  logs.value = [...logs.value, line].slice(-80)
}

function setBusy(show, title = '', hint = '', percent = 0) {
  busy.show = show
  busy.title = title
  busy.hint = hint
  busy.percent = percent
}

function applyTruck(data) {
  me.truckId = data.truckId
  me.driverName = data.driverName || me.driverName
  me.phone = data.phone || me.phone
  me.truckNumber = data.truckNumber || me.truckNumber
  me.capacityTons = data.capacityTons ?? me.capacityTons
  me.capacityM3 = data.capacityM3 ?? me.capacityM3
  me.vehicleType = data.vehicleType || me.vehicleType
  me.originCode = data.originCode || me.originCode
  me.originName = data.originName || me.originName
  me.destinationCode = data.destinationCode || me.destinationCode
  me.destinationName = data.destinationName || me.destinationName
  me.remainingVolumePercent = data.remainingVolumePercent ?? 100
  me.status = data.status || me.status
}

function saveSession() {
  sessionStorage.setItem('moveai_session', JSON.stringify({ ...me }))
}

function loadSession() {
  try {
    const raw = sessionStorage.getItem('moveai_session')
    if (!raw) return
    Object.assign(me, JSON.parse(raw))
    if (me.truckId) {
      gate.value = me.originCode && me.destinationCode ? 'app' : 'route'
      if (!me.vehicleType) gate.value = 'profile'
    }
  } catch (_) { /* ignore */ }
}

function logout() {
  sessionStorage.removeItem('moveai_session')
  Object.assign(me, {
    truckId: null, driverName: '', phone: '', truckNumber: '',
    originCode: '', originName: '', destinationCode: '', destinationName: '',
    remainingVolumePercent: 100, status: 'IDLE',
  })
  gate.value = 'login'
  tab.value = 'cargo'
  feed.value = []
  logs.value = []
}

async function doLogin() {
  if (!loginForm.phone || !loginForm.truckNumber) {
    toast.value = '차량번호와 전화번호를 입력하세요'
    return
  }
  setBusy(true, '접속 중', '기사 세션 확인', 30)
  message.value = ''
  try {
    const { data } = await api.post('/drivers/login', {
      phone: loginForm.phone,
      truckNumber: loginForm.truckNumber,
      driverName: loginForm.driverName || undefined,
    })
    applyTruck(data)
    profileForm.driverName = me.driverName || loginForm.driverName
    profileForm.capacityTons = me.capacityTons || 11
    profileForm.capacityM3 = me.capacityM3 || 50
    profileForm.vehicleType = me.vehicleType || '윙바디'
    profileForm.remainingVolumePercent = me.remainingVolumePercent ?? 100
    saveSession()
    if (data.needProfile) gate.value = 'profile'
    else if (data.needRoute) gate.value = 'route'
    else {
      gate.value = 'app'
      await Promise.all([loadFeed(), loadLedger()])
    }
    pushLog(data.message || '로그인 완료')
  } catch (e) {
    toast.value = e?.response?.data?.message || e.message
  } finally {
    setBusy(false)
  }
}

async function doProfile() {
  setBusy(true, '차량 등록', '프로필 저장', 40)
  try {
    const { data } = await api.post(`/drivers/${me.truckId}/profile`, { ...profileForm })
    applyTruck(data)
    saveSession()
    gate.value = data.needRoute ? 'route' : 'app'
    if (gate.value === 'app') await loadFeed()
  } catch (e) {
    toast.value = e.message
  } finally {
    setBusy(false)
  }
}

async function doRoute() {
  setBusy(true, '경로 저장', '출도착 터미널', 50)
  try {
    const { data } = await api.post(`/drivers/${me.truckId}/route`, {
      originCode: routeForm.originCode,
      destinationCode: routeForm.destinationCode,
    })
    applyTruck(data)
    saveSession()
    gate.value = 'app'
    tab.value = 'cargo'
    await loadFeed()
  } catch (e) {
    toast.value = e.message
  } finally {
    setBusy(false)
  }
}

async function loadStations() {
  const { data } = await api.get('/dispatch/stations')
  stations.value = data.stations || []
  if (!routeForm.originCode && stations.value[0]) routeForm.originCode = stations.value[0].code
}

async function loadFeed() {
  if (!me.truckId) return
  const { data } = await api.get('/dispatch/cargo-feed', { params: { truckId: me.truckId } })
  feed.value = data.items || []
  if (data.remainingVolumePercent != null) {
    me.remainingVolumePercent = data.remainingVolumePercent
    saveSession()
  }
}

async function loadLedger() {
  if (!me.truckId) return
  const { data } = await api.get('/dispatch/ledger', { params: { truckId: me.truckId } })
  ledger.value = data
}

async function onUpload(ev) {
  const file = ev.target.files?.[0]
  if (!file || !me.truckId) return
  setBusy(true, '상차 사진 분석', '잔여공간 측정 중', 15)
  pushLog(`업로드: ${file.name}`)
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('truckId', String(me.truckId))
    setBusy(true, '상차 사진 분석', 'AI 파이프라인', 55)
    const { data } = await api.post('/load/upload', form)
    me.remainingVolumePercent = data.remainingVolumePercent
    uploadGuide.value = data.guide || ''
    saveSession()
    const pipelineLogs = data.logs || []
    pipelineLogs.forEach((l) => pushLog(l))
    showLogs.value = true
    toast.value = `잔여 ${Number(data.remainingVolumePercent).toFixed(1)}% · ${data.status || '분석 완료'}`
    setBusy(true, '상차 사진 분석', '완료', 100)
  } catch (e) {
    toast.value = e?.response?.data?.message || e.message
    pushLog(`오류: ${toast.value}`)
  } finally {
    setTimeout(() => setBusy(false), 300)
    if (fileInput.value) fileInput.value.value = ''
  }
}

function goDrive() {
  tab.value = 'drive'
}

onMounted(async () => {
  loadSession()
  try {
    await loadStations()
  } catch (_) { /* ignore */ }
  if (gate.value === 'app' && me.truckId) {
    await Promise.all([loadFeed().catch(() => {}), loadLedger().catch(() => {})])
  }
  if (me.originCode) routeForm.originCode = me.originCode
  if (me.destinationCode) routeForm.destinationCode = me.destinationCode
})
</script>

<template>
  <div
    class="kakao-app"
    :class="{
      'drive-lock': gate === 'app' && tab === 'drive',
      'cargo-lock': gate === 'app' && tab === 'cargo',
    }"
  >
    <div v-if="busy.show" class="busy-overlay">
      <div class="busy-card shadow">
        <p class="busy-title">{{ busy.title }}</p>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: busy.percent + '%' }"></div>
        </div>
        <p class="busy-sub">{{ busy.percent }}% · {{ busy.hint }}</p>
      </div>
    </div>

    <div v-if="toast" class="toast shadow" @click="toast = null">
      <strong>알림</strong>
      <p>{{ toast }}</p>
    </div>

    <!-- 로그인 -->
    <section v-if="gate === 'login'" class="gate p-16">
      <h1 class="gate-brand">moveAI</h1>
      <p class="gate-desc">차량번호와 전화번호로 접속합니다. (세션별 로그인)</p>
      <label class="field">차량번호
        <input v-model="loginForm.truckNumber" placeholder="예: 서울 12가 3456" />
      </label>
      <label class="field">전화번호
        <input v-model="loginForm.phone" placeholder="01012345678" inputmode="tel" />
      </label>
      <label class="field">기사 이름 (선택)
        <input v-model="loginForm.driverName" placeholder="김기사" />
      </label>
      <button class="k-btn primary w-full" :disabled="busy.show" @click="doLogin">접속</button>
      <p v-if="message" class="desc subtle">{{ message }}</p>
    </section>

    <!-- 차량 등록 -->
    <section v-else-if="gate === 'profile'" class="gate p-16">
      <h2>차량 정보 등록</h2>
      <p class="gate-desc">{{ me.truckNumber }} · {{ me.phone }}</p>
      <label class="field">기사 이름
        <input v-model="profileForm.driverName" />
      </label>
      <label class="field">차량 톤수
        <select v-model.number="profileForm.capacityTons">
          <option :value="1">1톤</option>
          <option :value="2.5">2.5톤</option>
          <option :value="5">5톤</option>
          <option :value="8">8톤</option>
          <option :value="11">11톤</option>
          <option :value="18">18톤</option>
          <option :value="25">25톤</option>
        </select>
      </label>
      <label class="field">차종
        <select v-model="profileForm.vehicleType">
          <option>윙바디</option>
          <option>카고</option>
          <option>탑차</option>
          <option>트레일러</option>
        </select>
      </label>
      <label class="field">현재 잔여공간 (%)
        <input v-model.number="profileForm.remainingVolumePercent" type="number" min="0" max="100" />
      </label>
      <button class="k-btn primary w-full" :disabled="busy.show" @click="doProfile">등록 완료</button>
    </section>

    <!-- 출도착 -->
    <section v-else-if="gate === 'route'" class="gate p-16">
      <h2>오늘 운행 경로</h2>
      <p class="gate-desc">작업터미널을 선택해 운행 경로를 정합니다</p>
      <label class="field">출발 터미널
        <select v-model="routeForm.originCode" :disabled="!stations.length">
          <option disabled value="">선택</option>
          <option v-for="s in stations" :key="'ro-' + s.code" :value="s.code">{{ s.code }} · {{ s.name }}</option>
        </select>
      </label>
      <label class="field">도착 터미널
        <select v-model="routeForm.destinationCode" :disabled="!stations.length">
          <option disabled value="">선택</option>
          <option v-for="s in stations" :key="'rd-' + s.code" :value="s.code">{{ s.code }} · {{ s.name }}</option>
        </select>
      </label>
      <button
        class="k-btn primary w-full"
        :disabled="busy.show || !routeForm.originCode || !routeForm.destinationCode"
        @click="doRoute"
      >경로 저장 후 시작</button>
    </section>

    <!-- 메인 -->
    <template v-else>
      <header class="k-header">
        <div class="top-nav">
          <span class="brand">moveAI</span>
          <div class="me-chip">
            <span>{{ me.driverName || '기사' }}</span>
            <span class="sub">{{ me.truckNumber }}</span>
          </div>
          <button class="link-btn" @click="logout">로그아웃</button>
        </div>
        <p class="route-bar" @click="gate = 'route'">
          {{ me.originName || '출발' }} → {{ me.destinationName || '도착' }}
          · 계획 적재 {{ plannedOccupiedDisplay }}%
          <span class="edit">변경</span>
        </p>
      </header>

      <main class="k-main">
        <!-- 배차목록 -->
        <section v-show="tab === 'cargo'" class="tab-cargo">
          <div class="cargo-top">
            <h3>복화 배차</h3>
            <div class="mode-inline">
              <button type="button" class="mode-chip sm on">수동</button>
              <button type="button" class="mode-chip sm" disabled>LLM</button>
            </div>
            <button type="button" class="cart-badge empty">장바구니 0</button>
          </div>

          <div class="px-12 pt-8">
            <div class="status-card shadow mb-16">
              <div class="truck-info">
                <span class="tag">{{ me.vehicleType || '차량' }}</span>
                <span class="number">{{ me.capacityTons }}t · {{ me.capacityM3 }}m³</span>
                <span class="status-badge" :class="me.status">{{ me.status || 'IDLE' }}</span>
              </div>
              <div class="label-row">
                <span>잔여 공간</span>
                <span>{{ Number(me.remainingVolumePercent).toFixed(1) }}%</span>
              </div>
              <div class="progress-bar">
                <div class="fill" :style="{ width: Math.min(100, occupied) + '%' }"></div>
              </div>
              <div class="label-row sub">
                <span>적재율</span>
                <span>{{ occupied.toFixed(1) }}%</span>
              </div>
            </div>

            <div v-if="!feed.length" class="empty-box shadow">
              제안 물량이 없습니다.<br />
              <span class="desc subtle">배차 propose 연동 후 여기에 카드가 쌓입니다.</span>
            </div>
            <article
              v-for="item in feed"
              :key="item.requestId"
              class="cargo-card shadow"
            >
              <div class="cc-route">{{ item.origin }} → {{ item.destination }}</div>
              <div class="cc-meta">
                <span>{{ item.boxCount || 0 }}박스</span>
                <span class="plus">{{ formatWon(item.proposedFee) }}</span>
                <span v-if="item.fillPercentOf11t != null">점유 {{ item.fillPercentOf11t }}%</span>
              </div>
            </article>
          </div>
        </section>

        <!-- 운행 -->
        <section v-show="tab === 'drive'" class="tab-drive">
          <div class="drive-stage">
            <div class="map-container">
              <div class="map-placeholder">
                <p>카카오맵 연동 예정</p>
                <p class="hint">VITE_KAKAO_JS_KEY 설정 후 지도가 표시됩니다</p>
              </div>
              <div class="navi-overlay">
                <div class="direction">
                  <span>{{ me.originName || me.originCode || '출발' }}</span>
                  <span>→</span>
                  <span>{{ me.destinationName || me.destinationCode || '도착' }}</span>
                </div>
                <p class="next-step">잔여 {{ Number(me.remainingVolumePercent).toFixed(1) }}% · 계획 적재 {{ plannedOccupiedDisplay }}%</p>
              </div>
            </div>
            <div class="drive-dock">
              <div class="stop-panel shadow">
                <div class="stop-now">
                  <span class="stop-phase">운행 준비</span>
                  <span class="stop-idx">트럭 #{{ me.truckId }}</span>
                </div>
                <div class="stop-od">
                  <div class="stop-od-row">
                    <span class="od-tag from">출발</span>
                    <strong>{{ me.originName || me.originCode || '-' }}</strong>
                  </div>
                  <div class="stop-od-arrow">↓</div>
                  <div class="stop-od-row">
                    <span class="od-tag to">도착</span>
                    <strong>{{ me.destinationName || me.destinationCode || '-' }}</strong>
                  </div>
                </div>
                <div class="stop-actions">
                  <button type="button" class="k-btn outline photo-btn need" @click="fileInput?.click()">
                    상차 사진
                  </button>
                  <input ref="fileInput" type="file" accept="image/*" hidden @change="onUpload" />
                </div>
                <p v-if="uploadGuide" class="stop-hint">{{ uploadGuide }}</p>
                <p v-else class="stop-hint muted">상차 사진을 올리면 잔여공간이 갱신됩니다.</p>
              </div>
            </div>
          </div>
        </section>

        <!-- 정산 -->
        <section v-if="tab === 'ledger'" class="tab-content p-16">
          <div class="k-card shadow mb-16">
            <h3>나의 운행 정산</h3>
            <p class="desc subtle mb-8">배차 건별로 터미널·물량·금액을 확인할 수 있습니다.</p>
            <div class="ledger-grid">
              <div class="item"><label>합계 수입</label><p class="val plus">{{ formatWon(ledger.totalIncome) }}</p></div>
              <div class="item"><label>합계 지출</label><p class="val">{{ formatWon(ledger.totalExpense) }}</p></div>
              <div class="item"><label>순수익</label><p class="val plus">{{ formatWon(ledger.netProfit) }}</p></div>
              <div class="item"><label>ESG</label><p class="val esg">{{ ledger.dailyEsgKg || 0 }}kg</p></div>
            </div>
            <h4 class="ledger-sub">건별 내역 ({{ ledger.entryCount || ledger.entries?.length || 0 }}건)</h4>
            <div class="ledger-list" v-if="ledger.entries?.length">
              <article class="ledger-row" v-for="(e, idx) in ledger.entries" :key="e.id || idx">
                <div class="route">{{ e.route || '운행' }}</div>
                <div class="amt">
                  <span class="plus">운임 +{{ formatWon(e.income) }}</span>
                  <span>유류 {{ formatWon(e.expense) }}</span>
                  <span class="net">순 {{ formatWon(e.netProfit) }}</span>
                </div>
              </article>
            </div>
            <p v-else class="desc subtle">수락·배차된 건이 없습니다. 복화 배차 후 운행을 완료하면 여기에 쌓입니다.</p>
          </div>
        </section>

        <div v-show="tab !== 'cargo'" class="card log-container shadow">
          <div class="log-header" @click="showLogs = !showLogs">
            <span>처리 과정</span>
            <span class="log-toggle">{{ showLogs ? '접기 ▲' : '펼치기 ▼' }}</span>
          </div>
          <div v-if="showLogs" class="log-content">
            <p v-for="(log, i) in logs" :key="i">> {{ log }}</p>
            <p v-if="!logs.length">> 아직 로그가 없습니다</p>
          </div>
        </div>
      </main>

      <nav class="k-bottom-nav shadow">
        <div class="nav-item" :class="{ active: tab === 'cargo' }" @click="tab = 'cargo'; loadFeed()">
          <span class="label">배차목록</span>
        </div>
        <div class="nav-item" :class="{ active: tab === 'drive' }" @click="goDrive">
          <span class="label">운행</span>
        </div>
        <div class="nav-item" :class="{ active: tab === 'ledger' }" @click="tab = 'ledger'; loadLedger()">
          <span class="label">정산</span>
        </div>
      </nav>
    </template>
  </div>
</template>
