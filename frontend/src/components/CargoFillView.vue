<script setup>
/**
 * 적재함 등각 트럭 UI.
 * 주 fillPct는 실측값만 쓰고, 터미널별 색은 세그먼트로 누적 표시한다.
 */
import { computed } from 'vue'

const props = defineProps({
  capacityCbm: { type: Number, default: 50 },
  loadedCbm: { type: Number, default: 0 },
  fillPct: { type: Number, default: 0 },
  cargoWidthM: { type: Number, default: 2.35 },
  cargoLengthM: { type: Number, default: 9.3 },
  cargoHeightM: { type: Number, default: 2.45 },
  modelLabel: { type: String, default: '' },
  measured: { type: Boolean, default: false },
  /** 터미널별 적재 */
  terminalLoads: { type: Array, default: () => [] },
  truckTons: { type: [Number, String], default: 11 },
  truckNumber: { type: String, default: '' },
  statusText: { type: String, default: '' },
  statusKind: { type: String, default: 'IDLE' },
  plannedFillPct: { type: Number, default: 0 },
})

const PALETTE = [
  '#2f80ed', '#27ae60', '#f2994a', '#9b51e0',
  '#eb5757', '#56ccf2', '#219653', '#f2c94c',
]

const listLoads = computed(() => {
  const raw = Array.isArray(props.terminalLoads) ? props.terminalLoads : []
  return raw.map((row, idx) => {
    const planned = Math.max(0, Number(row.plannedPercent ?? 0) || 0)
    const hasM = row.measuredPercent != null && row.measuredPercent !== ''
    const measured = hasM ? Math.max(0, Number(row.measuredPercent) || 0) : null
    const role = row.role ? String(row.role) : ''
    return {
      name: row.name || row.terminalName || `${idx + 1}번`,
      role,
      fillPercent: measured != null ? measured : 0,
      plannedPercent: planned,
      measuredPercent: measured,
      color: row.color || PALETTE[idx % PALETTE.length],
    }
  })
})

/** 트럭 색 칸은 실측이 있는 구간만 */
const normalizedLoads = computed(() =>
  listLoads.value.filter((row) => (row.measuredPercent != null && row.measuredPercent > 0.001))
)

/** UI 격자: 길이 10칸 / 폭 3줄 / 높이 3단 */
const NX = 10
const NY = 3
const NZ = 3

const CX = 0.866
const CY = 0.5
const S = 22
const HZ = 20
const CAB_LEN = 2.0
const DECK = 0

function fillHue(pct) {
  const p = Math.max(0, Math.min(100, pct || 0))
  return Math.round(210 - (p / 100) * 210)
}

const hue = computed(() => fillHue(props.fillPct))

const px = (i, j) => (i - j) * S * CX
const py = (i, j, k) => (i + j) * S * CY - k * HZ + DECK * HZ
const pt = (i, j, k) => `${px(i, j)},${py(i, j, k)}`
const poly = (pts) => pts.map(([i, j, k]) => pt(i, j, k)).join(' ')

/** 캡쪽(i=0)부터 fillPct만큼 채움 */
function cellsFromFillPct(pct) {
  const total = NX * NY * NZ
  const n = Math.max(0, Math.min(total, Math.round((Math.max(0, pct) / 100) * total)))
  const list = []
  let left = n
  for (let i = 0; i < NX && left > 0; i++) {
    for (let j = 0; j < NY && left > 0; j++) {
      for (let k = 0; k < NZ && left > 0; k++) {
        list.push({ i, j, k })
        left--
      }
    }
  }
  return list
}

/**
 * 정차마다 색이 누적 채움(A -> A+B -> A+B+C).
 * 실측 세그먼트 전(사진 전)은 fillPct=0이라 칸을 비움.
 */
const cubes = computed(() => {
  const fill = Math.max(0, Math.min(100, Number(props.fillPct) || 0))
  if (fill <= 0) return []
  const slots = cellsFromFillPct(fill)
  const loads = props.measured ? normalizedLoads.value : []
  const plannedSum = loads.reduce((s, t) => s + t.fillPercent, 0)
  if (!loads.length || plannedSum <= 0) {
    return slots.map((c) => ({ ...c, color: null }))
  }
  const nFill = slots.length
  const quotas = loads.map((t) => ({
    ...t,
    n: Math.max(0, Math.round((t.fillPercent / plannedSum) * nFill)),
  }))
  let assigned = quotas.reduce((s, q) => s + q.n, 0)
  let qi = 0
  while (assigned < nFill && quotas.length) {
    quotas[qi % quotas.length].n += 1
    assigned += 1
    qi += 1
  }
  while (assigned > nFill && quotas.length) {
    const q = quotas[qi % quotas.length]
    if (q.n > 0) {
      q.n -= 1
      assigned -= 1
    }
    qi += 1
  }
  const out = []
  let offset = 0
  for (const q of quotas) {
    for (let i = 0; i < q.n && offset < slots.length; i++, offset++) {
      out.push({ ...slots[offset], color: q.color })
    }
  }
  while (offset < slots.length) {
    out.push({ ...slots[offset], color: quotas[quotas.length - 1]?.color || null })
    offset += 1
  }
  out.sort((a, b) => a.i + a.j + a.k - (b.i + b.j + b.k))
  return out
})

const floorGridLines = computed(() => {
  const lines = []
  for (let i = 0; i <= NX; i++) {
    lines.push({
      key: `fi${i}`,
      x1: px(i, 0), y1: py(i, 0, 0),
      x2: px(i, NY), y2: py(i, NY, 0),
    })
  }
  for (let j = 0; j <= NY; j++) {
    lines.push({
      key: `fj${j}`,
      x1: px(0, j), y1: py(0, j, 0),
      x2: px(NX, j), y2: py(NX, j, 0),
    })
  }
  return lines
})

const heightGridLines = computed(() => {
  const lines = []
  for (let k = 1; k < NZ; k++) {
    lines.push({
      key: `hk${k}`,
      x1: px(0, NY), y1: py(0, NY, k),
      x2: px(NX, NY), y2: py(NX, NY, k),
    })
    lines.push({
      key: `hs${k}`,
      x1: px(NX, 0), y1: py(NX, 0, k),
      x2: px(NX, NY), y2: py(NX, NY, k),
    })
  }
  for (let i = 1; i < NX; i++) {
    lines.push({
      key: `vi${i}`,
      x1: px(i, NY), y1: py(i, NY, 0),
      x2: px(i, NY), y2: py(i, NY, NZ),
    })
  }
  return lines
})

const viewBox = computed(() => {
  const cabFront = -CAB_LEN
  const xs = [px(cabFront, 0), px(NX, 0), px(cabFront, NY), px(NX, NY)]
  const ys = [py(0, 0, NZ + 0.4), py(NX, NY, 0) + 22]
  const minX = Math.min(...xs) - 16
  const maxX = Math.max(...xs) + 16
  const minY = Math.min(...ys) - 14
  const maxY = Math.max(...ys) + 14
  return `${minX} ${minY} ${maxX - minX} ${maxY - minY}`
})

const cabGeom = computed(() => {
  const cabFront = -CAB_LEN
  const cabH = Math.max(1.2, NZ * 0.72)
  const axles = [cabFront + 1.15, NX * 0.66, NX * 0.66 + 1.25]
  return { nx: NX, ny: NY, nz: NZ, cabFront, cabH, axles }
})

function face(pts) {
  return poly(pts)
}

const captionText = computed(() => {
  if (Number(props.fillPct) <= 0) {
    return '상차 사진 등록 후 적재율이 채워집니다'
  }
  const mid = String.fromCharCode(0x00b7)
  const cub = String.fromCharCode(0x00b3)
  return '실측 ' + Number(props.fillPct || 0).toFixed(1) + '% ' + mid + ' ' + Number(props.loadedCbm || 0).toFixed(1) + ' m' + cub + ' / ' + props.capacityCbm.toFixed(1) + ' m' + cub
})
</script>

<template>
  <div
    v-if="capacityCbm > 0"
    class="cargo-fill"
    :style="{ '--fill-hue': hue }"
  >
    <div class="cf-head">
      <span class="cf-title">적재 공간</span>
      <span class="cf-badge" :class="statusKind" v-if="statusText">{{ statusText }}</span>
    </div>

    <div class="cf-status" v-if="truckNumber">
      <div class="cf-truck-row">
        <span class="cf-tag">{{ truckTons }}톤</span>
        <span class="cf-num">{{ truckNumber }}</span>
      </div>
      <div class="cf-bar-row">
        <span>실측 적재</span>
        <b>{{ Number(fillPct || 0).toFixed(1) }}%</b>
      </div>
      <div class="cf-bar">
        <i :style="{ width: Math.min(100, Number(fillPct || 0)) + '%' }" />
      </div>
      <div class="cf-bar-row sub">
        <span>계획 적재(터미널 합계)</span>
        <span>{{ Number(plannedFillPct || 0).toFixed(1) }}%</span>
      </div>
    </div>

    <ul v-if="listLoads.length" class="cf-term-list">
      <li v-for="(row, idx) in listLoads" :key="idx">
        <i class="swatch" :style="{ background: row.color }" />
        <span class="cf-term-name">{{ idx + 1 }}번 · {{ row.role ? row.role + ' · ' : '' }}{{ row.name }}</span>
        <span class="cf-term-pct">
          계획 {{ row.plannedPercent.toFixed(1) }}%
          <template v-if="row.measuredPercent != null"> · 실측 {{ row.measuredPercent.toFixed(1) }}%</template>
          <template v-else> · 실측 -</template>
        </span>
      </li>
    </ul>
    <p v-else class="cf-term-empty">
      배차 확정 후 적재 계획이 표시됩니다
    </p>

    <svg
      :viewBox="viewBox"
      class="cf-svg"
      role="img"
      :aria-label="`적재함 점유 ${Number(fillPct || 0).toFixed(1)}%`"
    >
<polygon
        class="cf-wall far"
        :points="face([[0, 0, 0], [cabGeom.nx, 0, 0], [cabGeom.nx, 0, cabGeom.nz], [0, 0, cabGeom.nz]])"
      />
      <polygon
        class="cf-wall far"
        :points="face([[0, 0, 0], [0, cabGeom.ny, 0], [0, cabGeom.ny, cabGeom.nz], [0, 0, cabGeom.nz]])"
      />
      <polygon
        class="cf-floor"
        :points="face([[0, 0, 0], [cabGeom.nx, 0, 0], [cabGeom.nx, cabGeom.ny, 0], [0, cabGeom.ny, 0]])"
      />

      <g class="cf-gridlines">
        <line
          v-for="ln in floorGridLines"
          :key="ln.key"
          :x1="ln.x1" :y1="ln.y1" :x2="ln.x2" :y2="ln.y2"
        />
        <line
          v-for="ln in heightGridLines"
          :key="ln.key"
          :x1="ln.x1" :y1="ln.y1" :x2="ln.x2" :y2="ln.y2"
        />
      </g>

      <g
        v-for="c in cubes"
        :key="`${c.i}-${c.j}-${c.k}`"
        class="cf-cube"
        :style="c.color ? { '--cube-color': c.color } : undefined"
      >
        <polygon
          class="cf-top"
          :points="face([
            [c.i, c.j, c.k + 1], [c.i + 1, c.j, c.k + 1],
            [c.i + 1, c.j + 1, c.k + 1], [c.i, c.j + 1, c.k + 1],
          ])"
        />
        <polygon
          class="cf-right"
          :points="face([
            [c.i + 1, c.j, c.k], [c.i + 1, c.j + 1, c.k],
            [c.i + 1, c.j + 1, c.k + 1], [c.i + 1, c.j, c.k + 1],
          ])"
        />
        <polygon
          class="cf-left"
          :points="face([
            [c.i, c.j + 1, c.k], [c.i + 1, c.j + 1, c.k],
            [c.i + 1, c.j + 1, c.k + 1], [c.i, c.j + 1, c.k + 1],
          ])"
        />
      </g>

      <polygon
        class="cf-wall near"
        :points="face([
          [0, cabGeom.ny, 0], [cabGeom.nx, cabGeom.ny, 0],
          [cabGeom.nx, cabGeom.ny, cabGeom.nz], [0, cabGeom.ny, cabGeom.nz],
        ])"
      />
      <polygon
        class="cf-wall roof"
        :points="face([
          [0, 0, cabGeom.nz], [cabGeom.nx, 0, cabGeom.nz],
          [cabGeom.nx, cabGeom.ny, cabGeom.nz], [0, cabGeom.ny, cabGeom.nz],
        ])"
      />

      <g class="cf-frame">
        <polygon :points="face([[0, 0, 0], [cabGeom.nx, 0, 0], [cabGeom.nx, cabGeom.ny, 0], [0, cabGeom.ny, 0]])" />
        <polygon :points="face([[0, 0, cabGeom.nz], [cabGeom.nx, 0, cabGeom.nz], [cabGeom.nx, cabGeom.ny, cabGeom.nz], [0, cabGeom.ny, cabGeom.nz]])" />
        <line
          v-for="(p, idx) in [[0, 0], [cabGeom.nx, 0], [cabGeom.nx, cabGeom.ny], [0, cabGeom.ny]]"
          :key="'e' + idx"
          :x1="px(p[0], p[1])"
          :y1="py(p[0], p[1], 0)"
          :x2="px(p[0], p[1])"
          :y2="py(p[0], p[1], cabGeom.nz)"
        />
      </g>

      <polygon
        class="cf-door"
        :points="face([
          [cabGeom.nx, cabGeom.ny, 0], [cabGeom.nx + 1.5, cabGeom.ny + 1.1, 0],
          [cabGeom.nx + 1.5, cabGeom.ny + 1.1, cabGeom.nz], [cabGeom.nx, cabGeom.ny, cabGeom.nz],
        ])"
      />

      <g class="cf-truck">
        <polygon
          :points="face([
            [cabGeom.cabFront, 0, 0], [0, 0, 0], [0, cabGeom.ny, 0], [cabGeom.cabFront, cabGeom.ny, 0],
          ])"
        />
        <polygon
          class="cf-cab"
          :points="face([
            [cabGeom.cabFront, cabGeom.ny, 0], [0, cabGeom.ny, 0],
            [0, cabGeom.ny, cabGeom.cabH], [cabGeom.cabFront + 0.45, cabGeom.ny, cabGeom.cabH],
          ])"
        />
        <polygon
          class="cf-cab"
          :points="face([
            [cabGeom.cabFront, 0, 0], [cabGeom.cabFront, cabGeom.ny, 0],
            [cabGeom.cabFront + 0.45, cabGeom.ny, cabGeom.cabH], [cabGeom.cabFront + 0.45, 0, cabGeom.cabH],
          ])"
        />
        <polygon
          class="cf-cab"
          :points="face([
            [cabGeom.cabFront + 0.45, 0, cabGeom.cabH], [0, 0, cabGeom.cabH],
            [0, cabGeom.ny, cabGeom.cabH], [cabGeom.cabFront + 0.45, cabGeom.ny, cabGeom.cabH],
          ])"
        />
        <ellipse
          v-for="(wi, n) in cabGeom.axles"
          :key="'w' + n"
          class="cf-wheel"
          :cx="px(wi, cabGeom.ny)"
          :cy="py(wi, cabGeom.ny, 0) + 8"
          :rx="S * 0.4"
          :ry="S * 0.46"
        />
      </g>
    </svg>

    <p class="cf-caption">
      <b v-if="modelLabel">{{ modelLabel }} </b>
      {{ captionText }}
    </p>
  </div>
</template>

<style scoped>
.cargo-fill {
  --fill-color: hsl(var(--fill-hue, 210) 78% 52%);
  margin: 0;
  padding: 12px 14px 10px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}
.cf-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 2px;
}
.cf-title {
  font-size: 13px;
  font-weight: 800;
  color: #3c3c3c;
}
.cf-badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 12px;
  background: #f2f2f2;
  color: #555;
}
.cf-badge.MOVING { background: #e3f2fd; color: #1976d2; }
.cf-badge.LOADING { background: #fff3cd; color: #856404; }
.cf-status { margin: 8px 0 10px; }
.cf-truck-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.cf-tag {
  background: #eee;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
}
.cf-num { font-weight: 800; font-size: 13px; }
.cf-bar-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 700;
}
.cf-bar-row b { color: var(--fill-color); font-variant-numeric: tabular-nums; }
.cf-bar-row.sub { margin-top: 6px; color: #888; font-weight: 500; }
.cf-bar {
  height: 8px;
  background: #eee;
  border-radius: 4px;
  margin: 6px 0 2px;
  overflow: hidden;
}
.cf-bar i {
  display: block;
  height: 100%;
  background: #ffcd00;
  transition: width .3s;
}
.cf-term-list {
  list-style: none;
  margin: 0 0 6px;
  padding: 0;
  font-size: 11px;
  color: #666;
  line-height: 1.5;
}
.cf-term-list li {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 2px 0;
}
.cf-term-name { flex: 1; min-width: 0; font-weight: 600; color: #444; }
.cf-term-pct { flex-shrink: 0; font-variant-numeric: tabular-nums; color: #888; }
.cf-term-list .swatch {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}
.cf-term-empty {
  margin: 0 0 6px;
  font-size: 10px;
  color: #bbb;
}
.cf-svg {
  width: 100%;
  height: auto;
  display: block;
  max-height: 220px;
}
.cf-wall.far {
  fill: #f2f2f2;
  stroke: #ddd;
  stroke-width: 1;
}
.cf-wall.near {
  fill: var(--fill-color);
  opacity: 0.06;
  stroke: var(--fill-color);
  stroke-width: 1;
}
.cf-wall.roof {
  fill: var(--fill-color);
  opacity: 0.04;
  stroke: var(--fill-color);
  stroke-width: 1;
}
.cf-floor {
  fill: #e8e8e8;
  opacity: 0.55;
  stroke: none;
}
.cf-gridlines {
  fill: none;
  stroke: #b0b8c0;
  stroke-width: 0.7;
  opacity: 0.55;
  pointer-events: none;
}
.cf-frame {
  fill: none;
  stroke: var(--fill-color);
  stroke-width: 1.4;
  opacity: 0.65;
}
.cf-door {
  fill: var(--fill-color);
  opacity: 0.1;
  stroke: var(--fill-color);
  stroke-width: 1.1;
}
.cf-truck {
  fill: none;
  stroke: #bbb;
  stroke-width: 1.4;
}
.cf-truck .cf-cab {
  fill: #f7f7f7;
  stroke: #bbb;
  stroke-width: 1.4;
}
.cf-truck .cf-wheel {
  fill: #888;
  stroke: none;
  opacity: 0.45;
}
.cf-cube {
  --cube-color: var(--fill-color);
}
.cf-cube .cf-top {
  fill: var(--cube-color);
  opacity: 1;
  stroke: #fff;
  stroke-width: 0.45;
}
.cf-cube .cf-right {
  fill: var(--cube-color);
  opacity: 0.74;
  stroke: #fff;
  stroke-width: 0.45;
}
.cf-cube .cf-left {
  fill: var(--cube-color);
  opacity: 0.52;
  stroke: #fff;
  stroke-width: 0.45;
}
.cf-caption {
  font-size: 11px;
  color: #888;
  margin: 6px 0 0;
  line-height: 1.45;
}
.cf-caption b {
  color: #3c3c3c;
}
</style>
