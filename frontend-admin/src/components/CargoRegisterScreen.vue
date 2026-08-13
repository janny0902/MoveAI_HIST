<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  BOX_FREIGHT_BY_TYPE,
  BOX_TYPES,
  PRODUCT_CODES,
  analyzeFloorCargo,
  boxVolumeCbm,
  bridgeToDriverOdGroup,
  computeBoxFreight,
  fetchFillPreview,
  fetchTerminals,
  isBoxProduct,
  productLabel,
  registerWaybill,
  toWaybillPayload,
  uploadCargoPhoto,
} from '../lib/waybill'

const EMPTY_BOX = () => ({ boxType: 'A', boxWidthMm: '', boxDepthMm: '', boxHeightMm: '' })
const FILL_KEYS = ['3t', '5t', '11t', '18t', '1t', '2_5t', '8t', '25t']

function nowLocal() {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

function formatWon(n) {
  if (n == null || Number.isNaN(Number(n))) return '-'
  return `${Number(n).toLocaleString('ko-KR')}원`
}

const form = reactive({
  waybillNo: '',
  originTerminalCode: '',
  destinationTerminalCode: '',
  productCode: 'Box',
  productName: '박스',
  createdAt: nowLocal(),
  freightKrw: '',
  unitCount: '1',
})
const boxes = ref([EMPTY_BOX()])
const terminals = ref([])
const terminalError = ref('')
const busy = ref(false)
const analyzing = ref(false)
const message = ref('')
const error = ref('')
const asGroup = ref(false)
const photoPreview = ref(null)
const photoUrl = ref(null)
const photoFile = ref(null)
const analysis = ref(null)
const fillByVehicle = ref(null)
const fileRef = ref(null)

const boxMode = computed(() => isBoxProduct(form.productCode))
const volumes = computed(() => boxes.value.map(boxVolumeCbm))
const totalCbm = computed(() => volumes.value.reduce((sum, v) => sum + (v || 0), 0))
const autoFreight = computed(() => (boxMode.value ? computeBoxFreight(boxes.value) : 0))
const manualFee = computed(() => Number(form.freightKrw))
const freightOk = computed(() =>
  boxMode.value
  || (String(form.freightKrw).trim() !== '' && Number.isFinite(manualFee.value) && manualFee.value >= 0),
)
const ready = computed(() =>
  form.waybillNo.trim()
  && form.originTerminalCode
  && form.destinationTerminalCode
  && volumes.value.length > 0
  && volumes.value.every((v) => v !== null)
  && freightOk.value
  && (!asGroup.value || analysis.value != null || totalCbm.value > 0),
)
const fillRows = computed(() =>
  FILL_KEYS.map((k) => {
    const row = fillByVehicle.value?.[k]
    return row ? { key: k, ...row } : null
  }).filter(Boolean),
)

onMounted(async () => {
  try {
    const list = await fetchTerminals()
    terminals.value = list.map((t) => ({
      terminal_code: t.terminal_code || t.code,
      name: t.name || t.terminal_name || '',
    }))
    if (!form.originTerminalCode && terminals.value[0]) {
      form.originTerminalCode = terminals.value[0].terminal_code
    }
  } catch (e) {
    terminalError.value = e.message
  }
})

let fillTimer = null
watch([asGroup, totalCbm], () => {
  if (fillTimer) clearTimeout(fillTimer)
  if (!asGroup.value || !(totalCbm.value > 0)) {
    if (!analysis.value) fillByVehicle.value = null
    return
  }
  fillTimer = setTimeout(() => {
    fetchFillPreview(totalCbm.value)
      .then((data) => {
        fillByVehicle.value = data.fillByVehicle || data.fill_by_vehicle || null
      })
      .catch(() => {})
  }, 280)
})

function setProduct(code) {
  const found = PRODUCT_CODES.find((p) => p.code === code)
  form.productCode = code
  form.productName = found ? found.name : form.productName
  if (found?.autoFreight) form.freightKrw = ''
}

function addBox() {
  boxes.value = [...boxes.value, EMPTY_BOX()]
}
function removeBox(i) {
  boxes.value = boxes.value.filter((_, n) => n !== i)
}

function onToggleGroup(on) {
  asGroup.value = on
  if (!on) {
    photoPreview.value = null
    photoUrl.value = null
    photoFile.value = null
    analysis.value = null
    fillByVehicle.value = null
    if (fileRef.value) fileRef.value.value = ''
  }
}

async function onPickPhoto(e) {
  const file = e.target.files?.[0]
  if (!file) return
  error.value = ''
  message.value = ''
  analyzing.value = true
  photoPreview.value = URL.createObjectURL(file)
  photoFile.value = file
  try {
    const result = await analyzeFloorCargo(file)
    analysis.value = result
    photoUrl.value = result.photoUrl || result.photo_url || null
    boxes.value = [{
      boxType: 'A',
      boxWidthMm: String(result.box_width_mm ?? result.width_mm ?? ''),
      boxDepthMm: String(result.box_depth_mm ?? result.depth_mm ?? ''),
      boxHeightMm: String(result.box_height_mm ?? result.height_mm ?? ''),
    }]
    fillByVehicle.value = result.fill_by_vehicle || result.fillByVehicle || null
    if (!form.waybillNo.trim()) {
      form.waybillNo = `G${Date.now().toString().slice(-10)}`
    }
    message.value = result.guide || `치수 분석 완료 · ${(result.volume_m3 || 0).toFixed(3)} CBM`
  } catch (err) {
    analysis.value = null
    photoUrl.value = null
    error.value = err.message || String(err)
  } finally {
    analyzing.value = false
    if (fileRef.value) fileRef.value.value = ''
  }
}

async function submit() {
  if (!ready.value || busy.value) return
  busy.value = true
  message.value = ''
  error.value = ''
  try {
    let savedPhoto = photoUrl.value
    if (!savedPhoto && photoFile.value) {
      const up = await uploadCargoPhoto(photoFile.value)
      savedPhoto = up.photoUrl || up.photo_url || null
    }

    let matchingNote = ''
    try {
      await registerWaybill(toWaybillPayload(form, boxes.value))
      matchingNote = ' · matching 등록'
    } catch (matchErr) {
      matchingNote = ` · (matching 생략: ${matchErr.message || matchErr})`
    }

    const qty = boxMode.value
      ? (asGroup.value ? Math.max(1, boxes.value.length) : boxes.value.length)
      : Math.max(1, Number(form.unitCount) || 1)
    const fee = boxMode.value ? autoFreight.value : Math.round(manualFee.value)
    const pname = asGroup.value ? `${form.productName}(그룹사진)` : form.productName

    let odNote = ''
    try {
      const od = await bridgeToDriverOdGroup({
        waybillNo: form.waybillNo.trim(),
        originTerminalCode: form.originTerminalCode,
        destinationTerminalCode: form.destinationTerminalCode,
        boxCount: qty,
        volumeM3: totalCbm.value,
        productCode: form.productCode,
        productName: pname,
        freightKrw: fee,
        photoUrl: savedPhoto,
      })
      odNote = od?.message ? ` · ${od.message}` : ' · 기사 OD 반영'
    } catch (bridgeErr) {
      odNote = ` · (기사 반영 실패: ${bridgeErr.message || bridgeErr})`
    }

    const fill11 = fillByVehicle.value?.['11t']?.fillPercent
      ?? analysis.value?.fill_percent_of_11t
      ?? null
    message.value =
      `${form.waybillNo.trim()} ${asGroup.value ? '그룹 ' : ''}등록 — ${productLabel(form.productCode)} ${qty}` +
      (boxMode.value ? `개` : '개') +
      ` · 운임 ${formatWon(fee)} · 체적 ${totalCbm.value.toFixed(3)} CBM` +
      (fill11 != null ? ` · 11톤 ${fill11}%` : '') +
      odNote + matchingNote

    Object.assign(form, {
      waybillNo: '',
      productCode: 'Box',
      productName: '박스',
      createdAt: nowLocal(),
      freightKrw: '',
      unitCount: '1',
    })
    boxes.value = [EMPTY_BOX()]
    photoPreview.value = null
    photoUrl.value = null
    photoFile.value = null
    analysis.value = null
    fillByVehicle.value = null
    asGroup.value = false
  } catch (err) {
    error.value = err.message || String(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="card" @submit.prevent="submit">
    <label class="field-label">운송장번호</label>
    <input v-model="form.waybillNo" class="text-input" placeholder="301636574396" autocomplete="off" />

    <div class="grid-2">
      <div>
        <label class="field-label">출발 작업터미널</label>
        <select v-model="form.originTerminalCode" class="text-input" :disabled="!terminals.length">
          <option v-if="!terminals.length" value="">등록된 터미널 없음</option>
          <option v-for="t in terminals" :key="'o'+t.terminal_code" :value="t.terminal_code">
            {{ t.terminal_code }} · {{ t.name || '이름 없음' }}
          </option>
        </select>
      </div>
      <div>
        <label class="field-label">도착 작업터미널</label>
        <select v-model="form.destinationTerminalCode" class="text-input" :disabled="!terminals.length">
          <option value="">선택하세요</option>
          <option
            v-for="t in terminals.filter((x) => x.terminal_code !== form.originTerminalCode)"
            :key="'d'+t.terminal_code"
            :value="t.terminal_code"
          >
            {{ t.terminal_code }} · {{ t.name || '이름 없음' }}
          </option>
        </select>
      </div>
    </div>

    <label class="field-label">화물 옵션</label>
    <select class="text-input" :value="form.productCode" @change="setProduct($event.target.value)">
      <option v-for="p in PRODUCT_CODES" :key="p.code" :value="p.code">
        {{ p.name }}{{ p.autoFreight ? ' (운임 자동)' : ' (운임 직접입력)' }}
      </option>
    </select>

    <p v-if="boxMode" class="calc-line" style="margin-top:8px">
      자동 운임 <b>{{ formatWon(autoFreight) }}</b>
      <span class="sub"> — {{ Object.entries(BOX_FREIGHT_BY_TYPE).map(([k, v]) => `${k}:${v / 1000}천`).join(' · ') }}</span>
    </p>

    <div v-if="!boxMode" class="grid-2" style="margin-top:8px">
      <div>
        <label class="field-label">수량</label>
        <input v-model="form.unitCount" type="number" min="1" class="text-input" />
      </div>
      <div>
        <label class="field-label">화주 운임 (원) *</label>
        <input v-model="form.freightKrw" type="number" min="0" class="text-input" placeholder="45000" />
      </div>
    </div>

    <label class="field-label">생성일시</label>
    <input v-model="form.createdAt" type="datetime-local" class="text-input" />

    <label class="check-row">
      <input type="checkbox" :checked="asGroup" @change="onToggleGroup($event.target.checked)" />
      <span>
        <strong>그룹으로 등록</strong>
        <span class="sub"> — 바닥 적재 사진으로 치수·차종별 점유율 등록</span>
      </span>
    </label>

    <div v-if="asGroup" class="photo-group-panel">
      <div class="box-list-head">
        <span class="field-label" style="margin:0">바닥 적재 사진</span>
        <label class="btn compact primary" style="margin:0;cursor:pointer">
          {{ analyzing ? '분석 중…' : '사진 촬영 / 선택' }}
          <input
            ref="fileRef"
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            :disabled="analyzing || busy"
            @change="onPickPhoto"
          />
        </label>
      </div>
      <img v-if="photoPreview" :src="photoPreview" alt="적재 미리보기" class="floor-photo-preview" />
      <p v-if="analysis" class="calc-line">
        분석 치수
        <b>{{ analysis.width_mm || analysis.box_width_mm }}×{{ analysis.depth_mm || analysis.box_depth_mm }}×{{ analysis.height_mm || analysis.box_height_mm }} mm</b>
        · <b>{{ (analysis.volume_m3 || totalCbm).toFixed(3) }} CBM</b>
      </p>
    </div>

    <div class="box-list">
      <div class="box-list-head">
        <span class="field-label">{{ asGroup ? '그룹 치수 (mm)' : boxMode ? '박스 치수 (mm)' : '치수 (mm)' }}</span>
        <button v-if="!asGroup && boxMode" type="button" class="btn compact" @click="addBox">박스 추가</button>
      </div>

      <div v-for="(b, i) in boxes" :key="i" class="box-row">
        <select v-if="boxMode" v-model="b.boxType" class="text-input">
          <option v-for="t in BOX_TYPES" :key="t" :value="t">{{ t }} · {{ formatWon(BOX_FREIGHT_BY_TYPE[t]) }}</option>
        </select>
        <span v-else class="field-label" style="align-self:center;margin:0">{{ form.productName }}</span>
        <input v-model="b.boxWidthMm" type="number" class="text-input" placeholder="가로" min="1" />
        <input v-model="b.boxDepthMm" type="number" class="text-input" placeholder="세로" min="1" />
        <input v-model="b.boxHeightMm" type="number" class="text-input" placeholder="높이" min="1" />
        <button
          v-if="!asGroup && boxMode"
          type="button"
          class="btn compact ghost"
          :disabled="boxes.length === 1"
          @click="removeBox(i)"
        >✕</button>
      </div>

      <p class="calc-line">
        합계 체적 <b>{{ totalCbm.toFixed(3) }} CBM</b>
        <span class="sub"> — 가로×세로×높이 ÷ 10⁹</span>
      </p>
    </div>

    <div v-if="asGroup && fillRows.length" class="fill-table-wrap">
      <p class="field-label">차종별 점유율</p>
      <table class="fill-table">
        <thead><tr><th>차종</th><th>용량</th><th>점유</th></tr></thead>
        <tbody>
          <tr v-for="r in fillRows" :key="r.key" :class="{ emphasis: ['3t','5t','11t','18t'].includes(r.key) }">
            <td>{{ r.label || r.key }}</td>
            <td>{{ r.capacityM3 ?? r.capacity_m3 }} m³</td>
            <td><b>{{ r.fillPercent ?? r.fill_percent }}%</b></td>
          </tr>
        </tbody>
      </table>
    </div>

    <button type="submit" class="btn primary" :disabled="!ready || busy || analyzing">
      {{ busy ? '등록 중…' : asGroup ? '그룹 운송장 등록' : '운송장 등록' }}
    </button>

    <p v-if="message" class="ok-message">{{ message }}</p>
    <p v-if="error" class="dialog-error">{{ error }}</p>
    <p v-if="terminalError" class="dialog-error">{{ terminalError }}</p>
    <p class="hint">치수 입력 또는 그룹 사진으로 체적을 등록하면 기사 배차목록(PENDING)에 반영됩니다.</p>
  </form>
</template>

<style scoped>
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.check-row {
  display: flex; gap: 8px; align-items: flex-start;
  margin: 12px 0; font-size: 13px;
}
.box-list { margin-top: 8px; }
.box-list-head {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
}
.box-row {
  display: grid; grid-template-columns: 1.2fr 1fr 1fr 1fr auto; gap: 6px; margin: 8px 0;
}
.calc-line { font-size: 13px; margin: 8px 0; }
.calc-line .sub, .hint, .sub { color: var(--muted); font-size: 12px; }
.photo-group-panel {
  margin: 8px 0 12px; padding: 10px; border-radius: 12px; background: #fafafa; border: 1px solid var(--line);
}
.floor-photo-preview {
  display: block; width: 100%; max-height: 220px; object-fit: contain;
  margin-top: 8px; border-radius: 10px; background: #111;
}
.fill-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.fill-table th, .fill-table td { padding: 6px 4px; border-bottom: 1px solid var(--line); text-align: left; }
.fill-table tr.emphasis td { font-weight: 700; }
.btn.compact { width: auto; display: inline-block; padding: 8px 10px; font-size: 12px; margin-top: 0; }
.btn.compact.primary { background: var(--kakao-yellow); color: var(--kakao-black); }
.btn.ghost { background: transparent; border: 1px solid var(--line); }
</style>
