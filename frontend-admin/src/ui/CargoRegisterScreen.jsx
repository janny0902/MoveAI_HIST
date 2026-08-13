// [교체 가능] 화주사 운송장 등록 화면.
//
// 박스: 박스타입별 자동 운임. 행낭·파렛트 등: 화주 운임 직접 입력.
// 그룹 사진 등록 시 photoUrl 저장 → 기사앱 「적재물보기」.
import { useEffect, useMemo, useRef, useState } from "react";

import {
  BOX_TYPES,
  BOX_FREIGHT_BY_TYPE,
  PRODUCT_CODES,
  analyzeFloorCargo,
  boxVolumeCbm,
  bridgeToDriverOdGroup,
  computeBoxFreight,
  fetchFillPreview,
  fetchTerminals,
  isBoxProduct,
  productLabel,
  registerWaybill,
  toWaybillPayload,
  uploadCargoPhoto,
} from "../lib/waybill";

const EMPTY_BOX = { boxType: "A", boxWidthMm: "", boxDepthMm: "", boxHeightMm: "" };

function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

const emptyForm = () => ({
  waybillNo: "",
  originTerminalCode: "",
  destinationTerminalCode: "",
  productCode: "Box",
  productName: "박스",
  createdAt: nowLocal(),
  freightKrw: "",
  unitCount: "1",
});

const FILL_KEYS = ["3t", "5t", "11t", "18t", "1t", "2_5t", "8t", "25t"];

function formatWon(n) {
  if (n == null || Number.isNaN(Number(n))) return "-";
  return `${Number(n).toLocaleString("ko-KR")}원`;
}

export default function CargoRegisterScreen({ onDemoReset, demoBusy }) {
  const [form, setForm] = useState(emptyForm);
  const [boxes, setBoxes] = useState([{ ...EMPTY_BOX }]);
  const [terminals, setTerminals] = useState([]);
  const [terminalError, setTerminalError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [asGroup, setAsGroup] = useState(false);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [photoUrl, setPhotoUrl] = useState(null);
  const [photoFile, setPhotoFile] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [fillByVehicle, setFillByVehicle] = useState(null);
  const fileRef = useRef(null);

  const boxMode = isBoxProduct(form.productCode);

  useEffect(() => {
    let alive = true;
    fetchTerminals()
      .then((list) => {
        if (!alive) return;
        setTerminals(list);
        setForm((f) => (f.originTerminalCode ? f : { ...f, originTerminalCode: list[0]?.terminal_code || "" }));
      })
      .catch((err) => alive && setTerminalError(err.message));
    return () => { alive = false; };
  }, []);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const setProduct = (e) => {
    const code = e.target.value;
    const found = PRODUCT_CODES.find((p) => p.code === code);
    setForm((f) => ({
      ...f,
      productCode: code,
      productName: found ? found.name : f.productName,
      freightKrw: found?.autoFreight ? "" : f.freightKrw,
    }));
  };

  const setBox = (i, key) => (e) =>
    setBoxes((list) => list.map((b, n) => (n === i ? { ...b, [key]: e.target.value } : b)));

  const addBox = () => setBoxes((list) => [...list, { ...EMPTY_BOX }]);
  const removeBox = (i) => setBoxes((list) => list.filter((_, n) => n !== i));

  const volumes = useMemo(() => boxes.map(boxVolumeCbm), [boxes]);
  const totalCbm = volumes.reduce((sum, v) => sum + (v || 0), 0);
  const autoFreight = useMemo(() => (boxMode ? computeBoxFreight(boxes) : 0), [boxMode, boxes]);

  useEffect(() => {
    if (!asGroup || !(totalCbm > 0)) {
      if (!analysis) setFillByVehicle(null);
      return undefined;
    }
    let alive = true;
    const t = setTimeout(() => {
      fetchFillPreview(totalCbm)
        .then((data) => {
          if (!alive) return;
          setFillByVehicle(data.fillByVehicle || data.fill_by_vehicle || null);
        })
        .catch(() => {});
    }, 280);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [asGroup, totalCbm, analysis]);

  const manualFee = Number(form.freightKrw);
  // 금액은 0원 이상이면 등록 가능 (미입력 "" 만 불가)
  const freightOk = boxMode
    || (String(form.freightKrw).trim() !== "" && Number.isFinite(manualFee) && manualFee >= 0);

  const ready =
    form.waybillNo.trim() &&
    form.originTerminalCode &&
    form.destinationTerminalCode &&
    volumes.length > 0 &&
    volumes.every((v) => v !== null) &&
    freightOk &&
    (!asGroup || analysis != null || totalCbm > 0);

  const onToggleGroup = (e) => {
    const on = e.target.checked;
    setAsGroup(on);
    if (!on) {
      setPhotoPreview(null);
      setPhotoUrl(null);
      setPhotoFile(null);
      setAnalysis(null);
      setFillByVehicle(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onPickPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setMessage(null);
    setAnalyzing(true);
    setPhotoPreview(URL.createObjectURL(file));
    setPhotoFile(file);
    try {
      const result = await analyzeFloorCargo(file);
      setAnalysis(result);
      setPhotoUrl(result.photoUrl || result.photo_url || null);
      const w = result.box_width_mm ?? result.width_mm;
      const d = result.box_depth_mm ?? result.depth_mm;
      const h = result.box_height_mm ?? result.height_mm;
      setBoxes([{
        boxType: "A",
        boxWidthMm: String(w || ""),
        boxDepthMm: String(d || ""),
        boxHeightMm: String(h || ""),
      }]);
      setFillByVehicle(result.fill_by_vehicle || result.fillByVehicle || null);
      if (!form.waybillNo.trim()) {
        const stamp = Date.now().toString().slice(-10);
        setForm((f) => ({ ...f, waybillNo: `G${stamp}` }));
      }
      setMessage(result.guide || `치수 분석 완료 · ${(result.volume_m3 || 0).toFixed(3)} CBM`);
    } catch (err) {
      setAnalysis(null);
      setPhotoUrl(null);
      setError(err.message || String(err));
    } finally {
      setAnalyzing(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!ready || busy) return;
    if (asGroup && !analysis && !(totalCbm > 0)) {
      setError("그룹 등록은 사진 분석 또는 치수 입력이 필요합니다.");
      return;
    }
    if (!boxMode && !(String(form.freightKrw).trim() !== "" && Number.isFinite(manualFee) && manualFee >= 0)) {
      setError("행낭·파렛트 등 비박스 화물은 화주 운임(원)을 0 이상으로 입력해 주세요.");
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      let savedPhoto = photoUrl;
      if (!savedPhoto && photoFile) {
        const up = await uploadCargoPhoto(photoFile);
        savedPhoto = up.photoUrl || up.photo_url || null;
      }

      const result = await registerWaybill(toWaybillPayload(form, boxes));
      const qty = boxMode
        ? (asGroup ? Math.max(1, boxes.length) : boxes.length)
        : Math.max(1, Number(form.unitCount) || 1);
      const fee = boxMode ? autoFreight : Math.round(manualFee);
      const pname = asGroup ? `${form.productName}(그룹사진)` : form.productName;

      let odNote = "";
      try {
        const od = await bridgeToDriverOdGroup({
          waybillNo: form.waybillNo.trim(),
          originTerminalCode: form.originTerminalCode,
          destinationTerminalCode: form.destinationTerminalCode,
          boxCount: qty,
          volumeM3: totalCbm,
          productCode: form.productCode,
          productName: pname,
          freightKrw: fee,
          photoUrl: savedPhoto,
        });
        odNote = od?.message ? ` · ${od.message}` : " · 기사 OD 그룹 반영";
      } catch (bridgeErr) {
        odNote = ` · (기사 반영 실패: ${bridgeErr.message || bridgeErr})`;
      }

      const fill11 = fillByVehicle?.["11t"]?.fillPercent
        ?? analysis?.fill_percent_of_11t
        ?? null;
      setMessage(
        `${form.waybillNo.trim()} ${asGroup ? "그룹 " : ""}등록됨 — ${productLabel(form.productCode)} ${qty}` +
        (boxMode ? `개(${boxes.map((b) => b.boxType).join(",")})` : "개") +
        ` · 운임 ${formatWon(fee)} · 체적 ${totalCbm.toFixed(3)} CBM` +
        (fill11 != null ? ` · 11톤 ${fill11}%` : "") +
        odNote
      );
      setForm(emptyForm());
      setBoxes([{ ...EMPTY_BOX }]);
      setPhotoPreview(null);
      setPhotoUrl(null);
      setPhotoFile(null);
      setAnalysis(null);
      setFillByVehicle(null);
      setAsGroup(false);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const fillRows = FILL_KEYS
    .map((k) => {
      const row = fillByVehicle?.[k];
      if (!row) return null;
      return { key: k, ...row };
    })
    .filter(Boolean);

  return (
    <form className="card" onSubmit={submit}>
      {typeof onDemoReset === "function" && (
        <div className="box-list-head" style={{ marginBottom: 12 }}>
          <span className="field-label" style={{ margin: 0 }}>시연 데이터</span>
          <button
            type="button"
            className="btn compact secondary"
            disabled={demoBusy || busy}
            onClick={onDemoReset}
          >
            {demoBusy ? "초기화 중…" : "시연 리셋"}
          </button>
        </div>
      )}
      <label className="field-label" htmlFor="waybillNo">운송장번호</label>
      <input id="waybillNo" type="text" className="text-input" value={form.waybillNo}
             onChange={set("waybillNo")} autoComplete="off" inputMode="numeric"
             placeholder="301636574396" />

      <div className="grid-2">
        <div>
          <label className="field-label" htmlFor="originTerminalCode">출발 작업터미널</label>
          <select id="originTerminalCode" className="text-input" value={form.originTerminalCode}
                  onChange={set("originTerminalCode")} disabled={!terminals.length}>
            {!terminals.length && <option value="">등록된 터미널 없음</option>}
            {terminals.map((t) => (
              <option key={t.terminal_code} value={t.terminal_code}>
                {t.terminal_code} · {t.name || "이름 없음"}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="destinationTerminalCode">도착 작업터미널</label>
          <select id="destinationTerminalCode" className="text-input"
                  value={form.destinationTerminalCode}
                  onChange={set("destinationTerminalCode")} disabled={!terminals.length}>
            <option value="">선택하세요</option>
            {terminals
              .filter((t) => t.terminal_code !== form.originTerminalCode)
              .map((t) => (
                <option key={t.terminal_code} value={t.terminal_code}>
                  {t.terminal_code} · {t.name || "이름 없음"}
                </option>
              ))}
          </select>
        </div>
      </div>

      <label className="field-label" htmlFor="productCode">화물 옵션</label>
      <select id="productCode" className="text-input" value={form.productCode} onChange={setProduct}>
        {PRODUCT_CODES.map((p) => (
          <option key={p.code} value={p.code}>
            {p.name}{p.autoFreight ? " (운임 자동)" : " (운임 직접입력)"}
          </option>
        ))}
      </select>
      <p className="hint" style={{ marginTop: 6 }}>
        {boxMode
          ? "박스는 규격(S~E)별 단가로 자동 계산됩니다."
          : "행낭·파렛트 등은 화주 계약 운임을 직접 입력합니다."}
      </p>

      {!boxMode && (
        <div className="grid-2" style={{ marginTop: 8 }}>
          <div>
            <label className="field-label" htmlFor="unitCount">수량</label>
            <input id="unitCount" type="number" className="text-input" min="1" step="1"
                   value={form.unitCount} onChange={set("unitCount")} inputMode="numeric" />
          </div>
          <div>
            <label className="field-label" htmlFor="freightKrw">화주 운임 (원) *</label>
            <input id="freightKrw" type="number" className="text-input" min="0" step="1"
                   value={form.freightKrw} onChange={set("freightKrw")} inputMode="numeric"
                   placeholder="0 이상 (예: 45000)" required={!boxMode} />
          </div>
        </div>
      )}

      {boxMode && (
        <p className="calc-line" style={{ marginTop: 8 }}>
          자동 운임 <b>{formatWon(autoFreight)}</b>
          <span className="sub"> — 타입별 {Object.entries(BOX_FREIGHT_BY_TYPE).map(([k, v]) => `${k}:${(v / 1000).toFixed(v % 1000 ? 1 : 0)}천`).join(" · ")}</span>
        </p>
      )}

      <label className="field-label" htmlFor="createdAt">생성일시 (측정 시각)</label>
      <input id="createdAt" type="datetime-local" className="text-input"
             value={form.createdAt} onChange={set("createdAt")} />

      <label className="check-row">
        <input type="checkbox" checked={asGroup} onChange={onToggleGroup} />
        <span>
          <strong>그룹으로 등록</strong>
          <span className="sub"> — 바닥 적재 더미를 사진으로 찍어 가로·세로·높이·차종별 점유율로 등록</span>
        </span>
      </label>

      {asGroup && (
        <div className="photo-group-panel">
          <div className="box-list-head">
            <span className="field-label" style={{ margin: 0 }}>바닥 적재 사진</span>
            <label className="btn compact primary" style={{ margin: 0, cursor: analyzing ? "wait" : "pointer" }}>
              {analyzing ? "분석 중…" : "사진 촬영 / 선택"}
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                capture="environment"
                hidden
                disabled={analyzing || busy}
                onChange={onPickPhoto}
              />
            </label>
          </div>
          <p className="hint" style={{ marginTop: 8 }}>
            바닥에 쌓인 화물 전체가 보이게 찍어 주세요. 사진은 기사앱 「적재물보기」에 표시됩니다.
          </p>
          {photoPreview && (
            <img src={photoPreview} alt="적재 미리보기" className="floor-photo-preview" />
          )}
          {analysis && (
            <p className="calc-line">
              분석 치수 <b>{analysis.width_mm || analysis.box_width_mm}×{analysis.depth_mm || analysis.box_depth_mm}×{analysis.height_mm || analysis.box_height_mm} mm</b>
              {" · "}
              <b>{(analysis.volume_m3 || totalCbm).toFixed(3)} CBM</b>
              {photoUrl && <span className="sub"> · 사진 저장됨</span>}
            </p>
          )}
        </div>
      )}

      <div className="box-list">
        <div className="box-list-head">
          <span className="field-label">
            {asGroup ? "그룹 치수 (mm · 사진 분석값 수정 가능)" : boxMode ? "박스 치수 (mm)" : "치수 (mm · 점유율용)"}
          </span>
          {!asGroup && boxMode && (
            <button type="button" className="btn compact" onClick={addBox}>박스 추가</button>
          )}
        </div>

        {boxes.map((b, i) => (
          <div className={`box-row${asGroup ? " group-dims" : ""}`} key={i}>
            {boxMode ? (
              <select className="text-input" value={b.boxType} onChange={setBox(i, "boxType")}
                      aria-label={`${i + 1}번 박스 타입`}>
                {BOX_TYPES.map((t) => (
                  <option key={t} value={t}>{t} · {formatWon(BOX_FREIGHT_BY_TYPE[t])}</option>
                ))}
              </select>
            ) : (
              <span className="field-label" style={{ alignSelf: "center", margin: 0, whiteSpace: "nowrap" }}>
                {form.productName}
              </span>
            )}
            <input type="number" className="text-input" placeholder="가로" min="1" step="1"
                   value={b.boxWidthMm} onChange={setBox(i, "boxWidthMm")}
                   inputMode="numeric" aria-label={`${i + 1}번 가로(mm)`} />
            <input type="number" className="text-input" placeholder="세로" min="1" step="1"
                   value={b.boxDepthMm} onChange={setBox(i, "boxDepthMm")}
                   inputMode="numeric" aria-label={`${i + 1}번 세로(mm)`} />
            <input type="number" className="text-input" placeholder="높이" min="1" step="1"
                   value={b.boxHeightMm} onChange={setBox(i, "boxHeightMm")}
                   inputMode="numeric" aria-label={`${i + 1}번 높이(mm)`} />
            {!asGroup && boxMode && (
              <button type="button" className="btn compact ghost" onClick={() => removeBox(i)}
                      disabled={boxes.length === 1} aria-label={`${i + 1}번 삭제`}>✕</button>
            )}
          </div>
        ))}

        <p className="calc-line">
          {boxMode
            ? (asGroup ? "그룹" : `박스 ${boxes.length}개`)
            : `${form.productName} ${form.unitCount || 1}개`}
          {" · "}합계 체적 <b>{totalCbm.toFixed(3)} CBM</b>
          <span className="sub"> — 가로×세로×높이 ÷ 10⁹</span>
        </p>
      </div>

      {asGroup && fillRows.length > 0 && (
        <div className="fill-table-wrap">
          <p className="field-label">차종별 점유율 (등록 시 그룹에 저장)</p>
          <table className="fill-table">
            <thead>
              <tr>
                <th>차종</th>
                <th>용량</th>
                <th>점유</th>
              </tr>
            </thead>
            <tbody>
              {fillRows.map((r) => (
                <tr key={r.key} className={["3t", "5t", "11t", "18t"].includes(r.key) ? "emphasis" : ""}>
                  <td>{r.label || r.key}</td>
                  <td>{r.capacityM3 ?? r.capacity_m3} m³</td>
                  <td><b>{r.fillPercent ?? r.fill_percent}%</b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <button type="submit" className="btn primary" disabled={!ready || busy || analyzing}>
        {busy ? "등록 중…" : asGroup ? "그룹 운송장 등록" : "운송장 등록"}
      </button>

      {message && <p className="ok-message">{message}</p>}
      {error && <p className="dialog-error">{error}</p>}
      {terminalError && <p className="dialog-error">{terminalError}</p>}
      {!terminals.length && !terminalError && (
        <p className="dialog-error">
          출발 작업터미널이 없어 상차지를 정할 수 없습니다. 터미널을 먼저 등록해 주세요.
        </p>
      )}

      <p className="hint">
        박스만 규격 단가 자동 적용 · 그 외는 화주 금액 입력. 그룹 사진은 기사 복화 카드의 「적재물보기」로 확인합니다.
      </p>
    </form>
  );
}
