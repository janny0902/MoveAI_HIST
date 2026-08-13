// [교체 가능] CBM이 무엇인지 설명하는 도움말.
//
// 화면 전체가 CBM으로 말하는데 그 단위를 모르면 숫자가 그냥 숫자다. 물류를 오래 한
// 사람에게는 상식이지만, 이 화면을 보는 사람이 모두 그렇지는 않다.
//
// 접어 두는 이유: 아는 사람에게는 매번 자리를 차지하는 군더더기다. 필요한 사람만 편다.
import { useState } from "react";

export default function CbmHelpCard() {
  const [open, setOpen] = useState(false);

  return (
    <section className="card help">
      <button type="button" className="accordion" onClick={() => setOpen((v) => !v)}
              aria-expanded={open}>
        <span className="accordion-caret" aria-hidden="true">{open ? "▾" : "▸"}</span>
        <span className="accordion-title">CBM이 무엇인가요?</span>
        <span className="muted">{open ? "접기" : "펼치기"}</span>
      </button>

      {open && (
        <div className="help-body">
          <p>
            <b>CBM(Cubic Meter)</b>은 화물이 차지하는 <b>부피</b>를 세제곱미터(m³)로 나타낸
            단위입니다. 1 CBM은 가로·세로·높이가 각각 1m인 상자 하나의 부피입니다.
          </p>

          <p className="help-formula">
            가로(m) × 세로(m) × 높이(m) = CBM
          </p>

          <p>
            측정기는 밀리미터(mm)로 재므로 10<sup>9</sup>으로 나눠 CBM으로 바꿉니다.
            예를 들어 600 × 400 × 300mm 박스는 <b>0.072 CBM</b>입니다.
          </p>

          <div className="help-note">
            <b>cm를 m로 바꾸지 않는 실수</b>가 잦습니다. 120×80×100(cm)을 그대로 곱하면
            960,000이라는 값이 나옵니다. 반드시 100으로 나눠 미터로 바꾼 뒤 계산해야
            1.2 × 0.8 × 1.0 = 0.96 CBM이 됩니다.
          </div>

          <p>
            운임은 <b>부피와 무게 중 큰 쪽</b>으로 정해지는 것이 보통입니다. 가벼운데
            부피만 큰 화물(폴리백, 완충재를 채운 박스)은 무게가 아니라 CBM이 값을 정합니다.
          </p>

          <p className="help-lead">이 화면에서 CBM이 쓰이는 곳</p>
          <ul className="help-list">
            <li><b>적재함 체적</b> — 차 한 대가 담을 수 있는 총 부피</li>
            <li><b>적재율</b> — 실리는 부피 ÷ 적재함 체적</li>
            <li><b>묶음별 CBM</b> — 그 구간 물량이 차지하는 부피</li>
          </ul>

          <div className="help-note">
            <b>파렛트를 쓰면 계산이 달라집니다.</b> 화물만 재고 파렛트를 빼면 실제보다
            작게 잡힙니다. 깔판 높이(144mm)와 파렛트 규격(1,100×1,100mm)이 적재함에
            나누어떨어지지 않아 생기는 자투리까지 빼야 현장과 맞습니다 —
            '파렛트로 적재'를 켜면 그 기준으로 계산합니다.
          </div>
        </div>
      )}
    </section>
  );
}
