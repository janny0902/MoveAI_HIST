// [교체 가능] 화면 배치와 흐름 배선만 담당한다.
// 매칭 호출은 src/lib/useTruckMatch.js에 있다. 여기서 fetch를 직접 부르지 말 것.
//
// 이 화면은 기사가 운행하며 보는 화면이 아니라, 배차된 차에 물량을 얼마나 실을 수 있는지
// 관리자가 확인하는 화면이다. 그래서 목적지도, 운행 중 추적도 없다. 위치는 "지금 이 차가
// 어디 있나"를 확인하는 용도로만 보여준다.
//
// 사진 경로도 걷어냈다. 적재된 박스를 0으로 보기로 한 이상 실을 수 있는 공간은 등록
// 적재함 체적 그 자체라, 사진에서 빈 공간을 추정할 이유가 없다.
// (lib/useAnalysis.js와 ui/CaptureCard.jsx는 지우지 않고 남겨 뒀다 — 되돌릴 때 쓴다.)
import { useCallback, useState } from "react";

import { useTruckMatch } from "./lib/useTruckMatch";
import { loadPref, savePref } from "./lib/prefs";
import { resetDemoData } from "./lib/waybill";
import CargoListScreen from "./ui/CargoListScreen";
import CargoRegisterScreen from "./ui/CargoRegisterScreen";
import CbmHelpCard from "./ui/CbmHelpCard";
import ExplainCard from "./ui/ExplainCard";
import LocationCard from "./ui/LocationCard";
import MatchSummaryCard from "./ui/MatchSummaryCard";
import MyLocationCard from "./ui/MyLocationCard";
import TerminalGroupList from "./ui/TerminalGroupList";
import TruckMatchCard from "./ui/TruckMatchCard";

// 사용자가 둘이다. 관리자는 배차된 차에 물량을 배정하고, 화주사는 운송장을 등록한다.
const TABS = [
  { key: "capture", label: "관리자 · 적재 배정" },
  { key: "cargo", label: "화주사 · 등록" },
  { key: "list", label: "대기 운송장" },
];

export default function App() {
  const [tab, setTab] = useState("capture");
  // 기사는 같은 차로 하루에 여러 번 찍는다. 접속할 때마다 다시 고르게 하면 그 자체가
  // 오입력 기회고, 차량 번호는 틀리면 결과가 통째로 어긋난다.
  const [truckId, setTruckId] = useState(() => loadPref("truckId", "T-000001"));
  // 화면이 잡아 둔 위치. 매칭 직전에 서버 좌표를 이 값으로 갱신해, 화면에 보여준 좌표와
  // 실제로 쓰인 좌표가 어긋나지 않게 한다.
  const [gps, setGps] = useState(null);
  // 선택한 차량의 제원. 적재 그림이 실제 적재함 치수로 격자를 만든다.
  const [spec, setSpec] = useState(null);
  // 정렬 기준 위치. 주소로 직접 옮기면 GPS를 덮는다 — 관리자는 사무실에 앉아
  // "이 차가 여기서 출발한다 치고" 보는 일이 많다.
  const [override, setOverride] = useState(null);
  // 구간 필터. 여러 곳을 고를 수 있고, 고른 묶음만으로 적재율과 적재 그림을 다시 그린다.
  const [originFilter, setOriginFilter] = useState([]);
  const [destFilter, setDestFilter] = useState([]);
  // 후보 상한. 1만 건이 기본이다 — 20만 건 규모에서 4천 건만 보면 특정 구간이
  // 표본에 아예 안 들어와 "그 구간은 물량이 없다"로 보인다.
  const [candidateLimit, setCandidateLimit] = useState("10000");
  // 파렛트 적재가 기본이다. 실제 간선 운송이 파렛트 단위로 돌고, 깔판 높이와 바닥
  // 자투리를 빼지 않은 값은 현장에서 맞지 않는다.
  const [palletized, setPalletized] = useState(true);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoMsg, setDemoMsg] = useState(null);

  const { matching, busy, error, ranAt, run, reset } = useTruckMatch();

  const handleSpec = useCallback((s) => setSpec(s), []);

  // LocationCard가 watchPosition으로 계속 갱신한다. 참조가 매번 바뀌면 자식이
  // 무한 렌더되므로 콜백을 고정한다.
  const handleLocation = useCallback((state) => setGps(state), []);

  // 주소로 지정한 위치가 있으면 그것이 기준이고, 없으면 GPS를 쓴다.
  const basePosition = override?.position || gps?.position || null;

  // 고른 구간의 묶음과 그 합계. 집계 자체는 서버가 만든 값을 더하기만 한다.
  const allGroups = matching?.terminal_groups || [];
  const visibleGroups = allGroups.filter(
    (g) => (originFilter.length === 0 || originFilter.includes(g.origin_terminal_code))
        && (destFilter.length === 0 || destFilter.includes(g.destination_terminal_code))
  );
  const selection = {
    filtered: originFilter.length > 0 || destFilter.length > 0,
    volumeCbm: visibleGroups.reduce((s, g) => s + (g.volume_cbm || 0), 0),
    cargoCount: visibleGroups.reduce((s, g) => s + (g.cargo_count || 0), 0),
    weightKg: visibleGroups.reduce((s, g) => s + (g.weight_kg || 0), 0),
  };

  const changeTruckId = (id) => {
    setTruckId(id);
    savePref("truckId", id);
    // 다른 차의 결과를 그대로 두면 화면의 숫자가 어느 차 것인지 알 수 없다.
    reset();
    // 필터도 함께 푼다. 앞 차에만 있던 구간을 고른 채로 두면 결과가 빈 목록이 된다.
    setOriginFilter([]);
    setDestFilter([]);
  };

  // 자동 갱신은 없다. 주기적으로 다시 돌리면 화면을 보는 사이에 목록이 바뀌어,
  // 방금 판단한 묶음이 사라진다. 갱신 시점은 사람이 정한다.
  const runMatch = () =>
    run(truckId, basePosition, candidateLimit || undefined, palletized);

  const onDemoReset = async () => {
    if (demoBusy) return;
    if (!window.confirm("시연 데이터를 초기 상태로 되돌릴까요?\n(양방향 물량 재배치 · 차량 공차 · 정산 비움 · 기사 운행)")) return;
    setDemoBusy(true);
    setDemoMsg(null);
    try {
      const data = await resetDemoData();
      reset();
      setDemoMsg(data.message || `초기화 완료 · 그룹 ${data.groupsCreated ?? "-"}개`);
    } catch (err) {
      setDemoMsg(err.message || String(err));
    } finally {
      setDemoBusy(false);
    }
  };

  return (
    <>
      {/* 기사 화면(frontend)의 상단 브랜드 바와 같은 모양. 두 화면을 오가는 사람이
          같은 제품이라고 알아볼 수 있어야 한다 — 스타일 정의는 styles.css의 .k-header. */}
      <header className="k-header">
        <div className="k-header-inner">
          <span className="brand">moveAI</span>
          <span className="brand-tag">관리자</span>
          <button
            type="button"
            className="driver-link"
            onClick={() => { window.location.href = "/"; }}
          >
            기사 화면
          </button>
          <button
            type="button"
            className="driver-link demo-reset-btn"
            disabled={demoBusy}
            onClick={onDemoReset}
            title="시연용 물량·차량을 처음 상태로"
          >
            {demoBusy ? "초기화 중…" : "시연 리셋"}
          </button>
        </div>
      </header>

      <main className="app">
      <h1>화물칸 공간 분석</h1>
      {demoMsg && <p className={demoMsg.includes("실패") ? "dialog-error" : "ok-message"}>{demoMsg}</p>}

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={tab === t.key ? "tab active" : "tab"}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === "list" ? (
        <>
          <p className="sub">적재된 대기 운송장과 상차 터미널을 확인합니다.</p>
          <CargoListScreen />
        </>
      ) : tab === "cargo" ? (
        <>
          <p className="sub">체적이 측정된 운송장을 위치와 함께 등록합니다. 시연 리셋은 상단 버튼을 사용하세요.</p>
          <CargoRegisterScreen onDemoReset={onDemoReset} demoBusy={demoBusy} />
        </>
      ) : (
        <>
      <p className="sub">
        배차된 차를 고르고 버튼을 누르면 지금 실을 수 있는 물량과 적재율을 보여줍니다.
        적재함은 빈 차(0%) 기준으로 계산합니다.
      </p>

      {/* 목적지는 두지 않는다. 이 화면은 운행을 따라가는 화면이 아니라 배차 시점에
          "이 차에 얼마나 실리나"를 보는 화면이라, 필요한 것은 기준 위치뿐이다. */}
      <MyLocationCard
        position={basePosition}
        source={override ? override.label : (gps?.position ? "현재 위치" : null)}
        onChange={(position, label) => setOverride({ position, label })}
        onUseGps={() => setOverride(null)}
        gpsAvailable={Boolean(gps?.position)}
      />

      <LocationCard
        onLocation={handleLocation}
        override={override?.position || null}
        overrideLabel={override?.label}
      />

      <TruckMatchCard
        truckId={truckId}
        onTruckIdChange={changeTruckId}
        onRun={runMatch}
        onSpec={handleSpec}
        busy={busy}
        ranAt={ranAt}
        candidateLimit={candidateLimit}
        onCandidateLimitChange={setCandidateLimit}
        candidateLimitMax={matching?.candidate_limit_max}
        candidateLimitUsed={matching?.candidate_limit}
        palletized={palletized}
        onPalletizedChange={setPalletized}
      />

      {error && (
        <section className="card error" role="alert">
          {error}
        </section>
      )}

      {/* 실을 수 있는 게 없을 때 아무것도 안 그리면 버튼이 먹은 것처럼 보인다. */}
      {matching && !matching.can_load && (
        <section className="card notice">
          지금 실을 수 있는 운송장이 없습니다.
          {matching.failure_reason && (
            <span className="muted"> · 사유 {matching.failure_reason}</span>
          )}
        </section>
      )}

      <MatchSummaryCard matching={matching} spec={spec} selection={selection} />

      {/* CBM 도움말은 계산 과정 설명 바로 위에 둔다. 단위를 모르는 사람이 설명을 읽기
          직전에 만나야 뜻이 있고, 맨 위에 있으면 매번 지나쳐야 하는 군더더기가 된다. */}
      {matching && <CbmHelpCard />}

      <ExplainCard matching={matching} spec={spec} />

      <TerminalGroupList
        groups={visibleGroups}
        allGroups={allGroups}
        position={basePosition}
        originFilter={originFilter}
        destFilter={destFilter}
        onOriginChange={setOriginFilter}
        onDestChange={setDestFilter}
        onClear={() => { setOriginFilter([]); setDestFilter([]); }}
      />
        </>
      )}
      </main>
    </>
  );
}
