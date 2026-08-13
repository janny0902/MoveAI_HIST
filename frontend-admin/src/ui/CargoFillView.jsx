// [교체 가능] 적재 예정 물량을 실제 차량 제원에 맞춘 3D 그림으로 보여준다.
//
// 숫자만으로는 "17.7 CBM이 더 실린다"가 얼마나 되는 일인지 감이 오지 않는다. 관리자가
// 배차를 정할 때 필요한 것은 "이 차가 이만큼 찬다"는 그림이다.
//
// 격자는 등록 적재함 치수(가로x세로x높이)에서 만든다. 11톤 윙바디(2.35x9.30x2.45)와
// 1톤 탑차(1.67x2.83x1.81)는 길이 비가 3배 넘게 차이나는데, 같은 모양 상자에 채우면
// 그 차이가 그림에서 사라진다.
//
// 그리는 순서가 곧 깊이다(화가 알고리즘). 뒤쪽 벽 -> 바닥 -> 상자 -> 앞쪽 벽(반투명)
// 순으로 그려야 상자가 적재함 **안**에 있는 것처럼 보인다. 반투명 벽을 상자보다 먼저
// 그리면 상자가 차 밖에 붙은 것처럼 뜬다.
//
// 상자 개수는 **비율의 표현이지 실제 박스 개수가 아니다.** 운송장 수천 건을 낱개로
// 그리면 점이 되고, 실제 적재는 3D 빈패킹이라 이 격자와 다르다. 칸 수 대비 채운 칸 수가
// 적재율과 같아지도록만 맞추고, 그 사실은 캡션에 적는다.

// 등각 투영 상수. cos30 / sin30.
const CX = 0.866;
const CY = 0.5;
const S = 20;   // 격자 한 칸의 바닥 한 변
const HZ = 17;  // 격자 한 칸의 높이
const TARGET_CELLS = 260;

// 캡 길이(칸 단위)와 지면에서 적재함 바닥까지 띄우는 높이.
const CAB_LEN = 2.0;
const DECK = 0.55;

const px = (i, j) => (i - j) * S * CX;
const py = (i, j, k) => (i + j) * S * CY - k * HZ + DECK * HZ * 0;

/** 실제 치수에서 격자 칸 수를 만든다. 비율은 유지하고 총 칸 수만 TARGET에 맞춘다. */
function gridFromDims(w, l, h) {
  if (!(w > 0 && l > 0 && h > 0)) return { nx: 12, ny: 4, nz: 4 };
  const cell = Math.cbrt((w * l * h) / TARGET_CELLS);
  return {
    nx: Math.max(2, Math.round(l / cell)),
    ny: Math.max(1, Math.round(w / cell)),
    nz: Math.max(1, Math.round(h / cell)),
  };
}

/**
 * 적재율 -> 색상(HSL 색상환 각도). 0%는 파랑(210°), 100%는 빨강(0°).
 *
 * 중간에 초록·노랑을 지나는 경로라 "여유 -> 적당 -> 꽉 참"이 단계로 읽힌다. 채도와
 * 밝기는 고정해서, 색이 바뀌어도 상자 면끼리의 명암 대비(위/오른쪽/왼쪽)는 유지된다.
 */
export function fillHue(pct) {
  const p = Math.max(0, Math.min(100, pct || 0));
  return Math.round(210 - (p / 100) * 210);
}

const pt = (i, j, k) => `${px(i, j)},${py(i, j, k)}`;
const poly = (pts) => pts.map(([i, j, k]) => pt(i, j, k)).join(" ");

function Cube({ i, j, k }) {
  return (
    <g className="cf-cube">
      <polygon className="cf-top" points={poly([
        [i, j, k + 1], [i + 1, j, k + 1], [i + 1, j + 1, k + 1], [i, j + 1, k + 1]])} />
      <polygon className="cf-right" points={poly([
        [i + 1, j, k], [i + 1, j + 1, k], [i + 1, j + 1, k + 1], [i + 1, j, k + 1]])} />
      <polygon className="cf-left" points={poly([
        [i, j + 1, k], [i + 1, j + 1, k], [i + 1, j + 1, k + 1], [i, j + 1, k + 1]])} />
    </g>
  );
}

export default function CargoFillView({
  capacityCbm, loadedCbm, fillPct, cargoCount,
  cargoWidthM, cargoLengthM, cargoHeightM, modelLabel,
}) {
  if (!capacityCbm) return null;

  const { nx, ny, nz } = gridFromDims(cargoWidthM, cargoLengthM, cargoHeightM);
  const total = nx * ny * nz;
  const pct = Math.max(0, Math.min(100, fillPct || 0));
  const filledCells = loadedCbm > 0 ? Math.max(1, Math.round((pct / 100) * total)) : 0;

  // 앞(캡 쪽) 바닥부터 채운다. 실제 상차가 안쪽부터 쌓는 것과 같은 방향이다.
  const cubes = [];
  for (let n = 0; n < filledCells; n += 1) {
    const k = Math.floor(n / (nx * ny));
    const rest = n % (nx * ny);
    cubes.push({ i: Math.floor(rest / ny), j: rest % ny, k });
  }
  cubes.sort((a, b) => (a.i + a.j + a.k) - (b.i + b.j + b.k));

  const cabFront = -CAB_LEN;
  const cabH = Math.max(1.2, nz * 0.72);
  // 바퀴는 적재함 아래 가까운 쪽 모서리(j=ny)를 따라 놓는다. 앞축 하나 + 뒷축 둘.
  const axles = [cabFront + 1.15, nx * 0.66, nx * 0.66 + 1.25];

  const xs = [px(cabFront, 0), px(nx, 0), px(cabFront, ny), px(nx, ny)];
  const ys = [py(0, 0, nz + 0.4), py(nx, ny, 0) + 22];
  const minX = Math.min(...xs) - 16;
  const maxX = Math.max(...xs) + 16;
  const minY = Math.min(...ys) - 14;
  const maxY = Math.max(...ys) + 14;

  return (
    // 적재율이 오를수록 파랑 -> 빨강. 색 하나로 "여유 있다 / 꽉 찼다"가 먼저 읽힌다.
    // 색만으로 판단하게 두지는 않는다 — 같은 카드에 퍼센트 숫자가 항상 함께 있다.
    <div className="cargo-fill" style={{ "--fill-hue": fillHue(pct) }}>
      <svg viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`} className="cf-svg"
           role="img" aria-label={`적재함이 ${pct.toFixed(1)}퍼센트 찹니다`}>

        {/* 1) 뒤쪽 벽과 바닥 — 상자보다 먼저 그려 상자가 그 앞에 놓이게 한다 */}
        <polygon className="cf-wall far" points={poly([
          [0, 0, 0], [nx, 0, 0], [nx, 0, nz], [0, 0, nz]])} />
        <polygon className="cf-wall far" points={poly([
          [0, 0, 0], [0, ny, 0], [0, ny, nz], [0, 0, nz]])} />
        <polygon className="cf-floor" points={poly([
          [0, 0, 0], [nx, 0, 0], [nx, ny, 0], [0, ny, 0]])} />

        {/* 2) 상자 */}
        {cubes.map((c) => <Cube key={`${c.i}-${c.j}-${c.k}`} {...c} />)}

        {/* 3) 앞쪽 벽과 지붕 — 반투명. 상자가 안에 든 것처럼 보이게 한다 */}
        <polygon className="cf-wall near" points={poly([
          [0, ny, 0], [nx, ny, 0], [nx, ny, nz], [0, ny, nz]])} />
        <polygon className="cf-wall roof" points={poly([
          [0, 0, nz], [nx, 0, nz], [nx, ny, nz], [0, ny, nz]])} />

        {/* 4) 적재함 모서리선 */}
        <g className="cf-frame">
          <polygon points={poly([[0, 0, 0], [nx, 0, 0], [nx, ny, 0], [0, ny, 0]])} />
          <polygon points={poly([[0, 0, nz], [nx, 0, nz], [nx, ny, nz], [0, ny, nz]])} />
          {[[0, 0], [nx, 0], [nx, ny], [0, ny]].map(([i, j]) => (
            <line key={`${i}-${j}`} x1={px(i, j)} y1={py(i, j, 0)} x2={px(i, j)} y2={py(i, j, nz)} />
          ))}
        </g>

        {/* 5) 열린 뒷문 — 무엇의 뒤쪽인지 한눈에 잡아 준다 */}
        <polygon className="cf-door" points={poly([
          [nx, ny, 0], [nx + 1.5, ny + 1.1, 0], [nx + 1.5, ny + 1.1, nz], [nx, ny, nz]])} />

        {/* 6) 차대·캡·바퀴 */}
        <g className="cf-truck">
          <polygon points={poly([
            [cabFront, 0, 0], [0, 0, 0], [0, ny, 0], [cabFront, ny, 0]])} />
          <polygon className="cf-cab" points={poly([
            [cabFront, ny, 0], [0, ny, 0], [0, ny, cabH], [cabFront + 0.45, ny, cabH]])} />
          <polygon className="cf-cab" points={poly([
            [cabFront, 0, 0], [cabFront, ny, 0], [cabFront + 0.45, ny, cabH],
            [cabFront + 0.45, 0, cabH]])} />
          <polygon className="cf-cab" points={poly([
            [cabFront + 0.45, 0, cabH], [0, 0, cabH], [0, ny, cabH], [cabFront + 0.45, ny, cabH]])} />
          {axles.map((wi, n) => (
            <ellipse key={n} className="cf-wheel"
                     cx={px(wi, ny)} cy={py(wi, ny, 0) + 8} rx={S * 0.4} ry={S * 0.46} />
          ))}
        </g>
      </svg>

      <p className="cf-caption">
        {modelLabel && <b>{modelLabel} </b>}
        적재함 {capacityCbm.toFixed(2)} CBM 중 <b>{loadedCbm.toFixed(2)} CBM</b>이 찹니다
        {cargoCount != null && ` · 운송장 ${cargoCount}건`}
        <span className="cf-note">
          {" "}— 격자는 등록 적재함 치수({cargoLengthM?.toFixed?.(2)}×{cargoWidthM?.toFixed?.(2)}
          ×{cargoHeightM?.toFixed?.(2)}m)를 {nx}×{ny}×{nz}칸으로 나눈 것입니다.
          상자는 적재율({pct.toFixed(1)}%)을 칸으로 나타낸 것이고 실제 적재 배치는 아닙니다.
        </span>
      </p>
    </div>
  );
}
