<script setup>
import { onMounted, reactive, ref } from 'vue'
import {
  BOX_TYPES,
  PRODUCT_CODES,
  computeBoxFreight,
  fetchTerminals,
  isBoxProduct,
  registerWaybill,
  toWaybillPayload,
} from '../lib/waybill'

const terminals = ref([])
const msg = ref('')
const busy = ref(false)
const form = reactive({
  waybillNo: '',
  originTerminalCode: '',
  destinationTerminalCode: '',
  productCode: 'Box',
  productName: '박스',
  createdAt: '',
})
const boxes = ref([{ boxType: 'A', boxWidthMm: 400, boxDepthMm: 300, boxHeightMm: 300, qty: 1 }])

onMounted(async () => {
  try {
    terminals.value = await fetchTerminals()
    if (terminals.value[0]) {
      form.originTerminalCode = terminals.value[0].code || terminals.value[0].terminal_code || ''
      form.destinationTerminalCode =
        terminals.value[1]?.code || terminals.value[1]?.terminal_code || form.originTerminalCode
    }
  } catch (e) {
    msg.value = e.message
  }
})

function onProductChange() {
  const p = PRODUCT_CODES.find((x) => x.code === form.productCode)
  form.productName = p?.name || form.productCode
}

async function submit() {
  busy.value = true
  msg.value = ''
  try {
    const expanded = []
    for (const b of boxes.value) {
      const n = Math.max(1, Number(b.qty) || 1)
      for (let i = 0; i < n; i += 1) expanded.push(b)
    }
    const payload = toWaybillPayload(form, expanded)
    if (isBoxProduct(form.productCode)) {
      payload.freight_krw = computeBoxFreight(expanded)
    }
    const res = await registerWaybill(payload)
    msg.value = `등록 완료 · ${res.waybill_no || form.waybillNo}`
  } catch (e) {
    msg.value = e.message || String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="card">
    <label class="field-label">운송장 번호</label>
    <input v-model="form.waybillNo" class="text-input" placeholder="WB-20260813-001" />

    <label class="field-label">출발 터미널</label>
    <select v-model="form.originTerminalCode" class="text-input">
      <option v-for="t in terminals" :key="'o'+ (t.code || t.terminal_code)" :value="t.code || t.terminal_code">
        {{ t.code || t.terminal_code }} · {{ t.name || t.terminal_name || '' }}
      </option>
    </select>

    <label class="field-label">도착 터미널</label>
    <select v-model="form.destinationTerminalCode" class="text-input">
      <option v-for="t in terminals" :key="'d'+ (t.code || t.terminal_code)" :value="t.code || t.terminal_code">
        {{ t.code || t.terminal_code }} · {{ t.name || t.terminal_name || '' }}
      </option>
    </select>

    <label class="field-label">상품</label>
    <select v-model="form.productCode" class="text-input" @change="onProductChange">
      <option v-for="p in PRODUCT_CODES" :key="p.code" :value="p.code">{{ p.name }}</option>
    </select>

    <div v-for="(b, idx) in boxes" :key="idx" class="box-row">
      <select v-model="b.boxType" class="text-input sm">
        <option v-for="t in BOX_TYPES" :key="t" :value="t">{{ t }}</option>
      </select>
      <input v-model.number="b.boxWidthMm" type="number" class="text-input sm" placeholder="W mm" />
      <input v-model.number="b.boxDepthMm" type="number" class="text-input sm" placeholder="D mm" />
      <input v-model.number="b.boxHeightMm" type="number" class="text-input sm" placeholder="H mm" />
      <input v-model.number="b.qty" type="number" min="1" class="text-input sm" placeholder="수량" />
    </div>

    <button type="button" class="btn" :disabled="busy || !form.waybillNo" @click="submit">
      {{ busy ? '등록 중…' : '운송장 등록' }}
    </button>
    <p v-if="msg" :class="msg.includes('완료') ? 'ok-message' : 'dialog-error'">{{ msg }}</p>
  </section>
</template>

<style scoped>
.box-row {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin: 10px 0;
}
.text-input.sm { padding: 8px; font-size: 12px; }
.field-label { margin-top: 10px; }
</style>
