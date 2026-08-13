// [교체 가능] 표현 계층.
// 계약: steps는 { [stepKey]: "active" | "done" | "fail" } 형태이고, STEPS 배열이 순서를 정한다.
//
// 도는 중인 단계에는 남은 시간을 함께 보여준다. AI 공간 분석은 60-105초 걸리는데
// 그동안 화면에 아무 변화가 없어 고장난 것처럼 보인다는 지적이 있었다.
import { useEffect, useState } from "react";

import { STEPS } from "../lib/useAnalysis";

const MARK = { todo: "○", active: "◐", done: "●", fail: "✕" };

/** 예상 시간을 넘기면 남은 초를 지어내지 않는다. 0을 띄워 놓고 계속 도는 게 제일 나쁘다. */
function waitText(elapsed, eta) {
  if (eta == null) return null;
  const left = eta - elapsed;
  if (left > 0) return `약 ${left}초 남음`;
  return `예상보다 오래 걸리고 있습니다 (${elapsed}초 경과)`;
}

export default function ProgressList({ steps, stepStartedAt }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!stepStartedAt) { setElapsed(0); return; }
    setElapsed(0);
    const id = setInterval(
      () => setElapsed(Math.floor((Date.now() - stepStartedAt) / 1000)),
      1000
    );
    return () => clearInterval(id);
  }, [stepStartedAt]);

  if (!Object.keys(steps).length) return null;

  return (
    <section className="card">
      <ul className="steps">
        {STEPS.map(({ key, label, etaSeconds }) => {
          const state = steps[key] || "todo";
          const wait = state === "active" ? waitText(elapsed, etaSeconds) : null;
          return (
            <li key={key} data-state={state}>
              <span className="mark">{MARK[state]}</span>
              <span>{label}</span>
              {wait && <span className="step-eta">{wait}</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
