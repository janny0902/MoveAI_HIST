// [교체 가능] 운행 중 재매칭 상태.
//
// 사진은 한 번만 찍지만 트럭이 움직이면 주변 화물이 바뀐다. 목적지에 닿을 때까지
// 주기적으로 다시 계산하고, 기사가 원하면 언제든 멈출 수 있어야 한다 — 하차 준비
// 중이거나 더 받을 생각이 없을 때 계속 추천이 뜨면 방해가 된다.
import { useEffect, useState } from "react";

const END_TEXT = {
  arrived: "목적지에 도착해 추가 매칭을 멈췄습니다.",
  stopped: "기사님이 추가 매칭을 멈췄습니다.",
  restarted: "새로 촬영해 이전 운행의 매칭을 멈췄습니다.",
};

export default function TrackingCard({ tracking, intervalMs = 60000, onStop }) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!tracking?.active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [tracking?.active]);

  if (!tracking) return null;

  if (!tracking.active) {
    return (
      <section className="card notice">
        {END_TEXT[tracking.endReason] || "추가 매칭이 멈췄습니다."}
        {tracking.count > 0 && ` 운행 중 ${tracking.count}회 다시 계산했습니다.`}
      </section>
    );
  }

  const left = Math.max(0, Math.ceil((tracking.lastAt + intervalMs - now) / 1000));

  return (
    <section className="card tracking">
      <div className="tracking-head">
        <span className="tracking-dot" aria-hidden="true" />
        <span>운행 중 추가 매칭 확인 중</span>
        <span className="tracking-next">{left}초 후 갱신</span>
      </div>
      <p className="hint">
        목적지에 도착할 때까지 위치가 바뀔 때마다 실을 수 있는 화물을 다시 찾습니다.
        {tracking.count > 0 && ` 지금까지 ${tracking.count}회 갱신했습니다.`}
      </p>
      <button type="button" className="btn secondary" onClick={() => onStop("stopped")}>
        추가 매칭 중단
      </button>
    </section>
  );
}
