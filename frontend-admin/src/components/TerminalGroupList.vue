<script setup>
import { computed } from 'vue'

const props = defineProps({
  groups: { type: Array, default: () => [] },
  allGroups: { type: Array, default: () => [] },
  originFilter: { type: Array, default: () => [] },
  destFilter: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:originFilter', 'update:destFilter', 'clear'])

const origins = computed(() =>
  [...new Set(props.allGroups.map((g) => g.origin_terminal_code).filter(Boolean))].sort(),
)
const dests = computed(() =>
  [...new Set(props.allGroups.map((g) => g.destination_terminal_code).filter(Boolean))].sort(),
)

function toggle(list, code, which) {
  const next = list.includes(code) ? list.filter((c) => c !== code) : [...list, code]
  if (which === 'o') emit('update:originFilter', next)
  else emit('update:destFilter', next)
}
</script>

<template>
  <section v-if="allGroups.length" class="card">
    <div class="location-head">
      <h2 class="card-title">터미널 그룹</h2>
      <button
        v-if="originFilter.length || destFilter.length"
        type="button"
        class="linkish"
        @click="emit('clear')"
      >필터 해제</button>
    </div>

    <div class="filter-block">
      <p class="field-label">출발</p>
      <div class="chip-row">
        <button
          v-for="code in origins"
          :key="'o'+code"
          type="button"
          class="chip"
          :class="{ on: originFilter.includes(code) }"
          @click="toggle(originFilter, code, 'o')"
        >{{ code }}</button>
      </div>
      <p class="field-label">도착</p>
      <div class="chip-row">
        <button
          v-for="code in dests"
          :key="'d'+code"
          type="button"
          class="chip"
          :class="{ on: destFilter.includes(code) }"
          @click="toggle(destFilter, code, 'd')"
        >{{ code }}</button>
      </div>
    </div>

    <ul class="group-list">
      <li v-for="(g, i) in groups" :key="i">
        <strong>{{ g.origin_terminal_code }} → {{ g.destination_terminal_code }}</strong>
        <span>{{ Number(g.volume_cbm || 0).toFixed(2) }} CBM · {{ g.cargo_count || 0 }}건</span>
      </li>
      <li v-if="!groups.length" class="muted">필터 조건에 맞는 그룹이 없습니다.</li>
    </ul>
  </section>
</template>

<style scoped>
.card-title { margin: 0; font-size: 15px; font-weight: 800; }
.linkish {
  border: none; background: none; color: var(--accent-ink);
  font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit;
}
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; }
.chip {
  border: 1px solid var(--line-strong); background: #fff; border-radius: 8px;
  padding: 6px 8px; font-size: 11px; font-weight: 700; cursor: pointer; font-family: inherit;
}
.chip.on { border-color: var(--kakao-yellow); background: #fff9e0; }
.group-list { list-style: none; margin: 0; padding: 0; }
.group-list li {
  display: flex; flex-direction: column; gap: 2px;
  padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 13px;
}
.group-list span { color: var(--muted); font-size: 12px; }
</style>
