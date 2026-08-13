// [교체 가능] 화면 맨 위 요약 띠.
//
// 결과 카드는 사진·지도·진행목록 아래에 있어서, 운행 중에 결론을 보려면 매번
// 스크롤해야 했다. 기사가 알아야 할 한 줄(실을 수 있나 / 몇 건 / 얼마나 남았나)을
// 맨 위에 고정한다. 아래 결과 카드가 근거이고, 이건 결론만 보여준다.
export default function StatusBanner({ vision, matching, tracking }) {
  if (!vision && !matching) return null;

  const canLoad = Boolean(matching?.can_load);
  const cargos = matching?.selected_cargos || [];
  const cbm = cargos.reduce((s, c) => s + (c.volume_cbm || 0), 0);
  const kg = cargos.reduce((s, c) => s + (c.weight_kg || 0), 0);

  return (
    <section className={`status-banner ${canLoad ? "ok" : "bad"}`}>
      <div className="status-main">
        <strong>{canLoad ? "추가 상차 가능" : "추가 상차 불가"}</strong>
        {canLoad && (
          <span className="status-figure">
            {cargos.length}건 · {cbm.toFixed(2)} CBM · {Math.round(kg)} kg
          </span>
        )}
      </div>
      <div className="status-sub">
        {matching?.usable_free_cbm != null && (
          <span>남은 공간 {Number(matching.final_free_cbm ?? matching.usable_free_cbm).toFixed(2)} CBM</span>
        )}
        {matching?.remaining_weight_kg != null && (
          <span>남은 중량 {Math.round(matching.remaining_weight_kg - kg)} kg</span>
        )}
        {tracking?.active && <span className="status-live">운행 중 갱신</span>}
      </div>
    </section>
  );
}
