<script setup>
import { onMounted, ref } from 'vue'
import { fetchPendingCargos, shortTime } from '../lib/cargoList'
import { fetchTerminals } from '../lib/waybill'

const rows = ref([])
const terminals = ref([])
const terminalCode = ref('')
const destCode = ref('')
const page = ref(1)
const total = ref(0)
const busy = ref(false)
const error = ref('')

async function load() {
  busy.value = true
  error.value = ''
  try {
    const data = await fetchPendingCargos({
      terminalCode: terminalCode.value,
      destinationTerminalCode: destCode.value,
      page: page.value,
      limit: 50,
    })
    rows.value = data.cargos || []
    total.value = data.total ?? rows.value.length
  } catch (e) {
    error.value = e.message
    rows.value = []
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    terminals.value = await fetchTerminals()
  } catch (_) { /* optional */ }
  await load()
})
</script>

<template>
  <section class="card">
    <div class="filters">
      <select v-model="terminalCode" class="text-input" @change="page = 1; load()">
        <option value="">출발 전체</option>
        <option v-for="t in terminals" :key="'o'+ (t.code || t.terminal_code)" :value="t.code || t.terminal_code">
          {{ t.code || t.terminal_code }}
        </option>
      </select>
      <select v-model="destCode" class="text-input" @change="page = 1; load()">
        <option value="">도착 전체</option>
        <option v-for="t in terminals" :key="'d'+ (t.code || t.terminal_code)" :value="t.code || t.terminal_code">
          {{ t.code || t.terminal_code }}
        </option>
      </select>
      <button type="button" class="btn" :disabled="busy" @click="load">{{ busy ? '불러오는 중…' : '새로고침' }}</button>
    </div>

    <p v-if="error" class="dialog-error">{{ error }}</p>
    <p class="muted">총 {{ total }}건</p>

    <ul class="cargo-list">
      <li v-for="c in rows" :key="c.cargo_id || c.waybill_no">
        <strong>{{ c.waybill_no || c.cargo_id }}</strong>
        <span>{{ c.origin_terminal_code || '?' }} → {{ c.destination_terminal_code || '?' }}</span>
        <span class="muted">
          {{ c.volume_cbm != null ? Number(c.volume_cbm).toFixed(3) + ' CBM' : '' }}
          <template v-if="c.created_at || c.deadline_at"> · {{ shortTime(c.created_at || c.deadline_at) }}</template>
        </span>
      </li>
      <li v-if="!busy && !rows.length" class="muted">대기 운송장이 없습니다.</li>
    </ul>
  </section>
</template>

<style scoped>
.filters { display: grid; gap: 8px; margin-bottom: 10px; }
.cargo-list { list-style: none; margin: 0; padding: 0; }
.cargo-list li {
  display: flex; flex-direction: column; gap: 2px;
  padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 13px;
}
</style>
