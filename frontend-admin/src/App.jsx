const cfg = () => window.__MOVEAI_ADMIN__ || {}

export default function App() {
  const c = cfg()
  return (
    <div className="page">
      <header>
        <strong>moveAI /admin</strong>
        <span>적재 배정 시뮬 (초기 구축)</span>
      </header>
      <main>
        <section>
          <h1>관리자 용량 시뮬</h1>
          <p>
            기사 앱의 위치·20km 복화와 분리된 화면입니다.
            Vision / Matching Cloud Run URL은 런타임 <code>config.js</code>로 주입됩니다.
          </p>
          <dl>
            <div>
              <dt>VISION_BASE_URL</dt>
              <dd>{c.VISION_BASE_URL || '(미설정)'}</dd>
            </div>
            <div>
              <dt>MATCHING_BASE_URL</dt>
              <dd>{c.MATCHING_BASE_URL || '(미설정)'}</dd>
            </div>
            <div>
              <dt>KAKAO_JS_KEY</dt>
              <dd>{c.KAKAO_JS_KEY ? '설정됨' : '(미설정)'}</dd>
            </div>
          </dl>
        </section>
      </main>
    </div>
  )
}
