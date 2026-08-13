// [교체 가능] 촬영 전 현재 위치 표시.
//
// 카카오 JavaScript 키가 있으면 지도를, 없으면 주소/좌표 패널을 보여준다. 어느 쪽이든
// 기사가 "지금 잡힌 위치가 맞나"를 사진을 올리기 전에 확인할 수 있으면 목적을 다한 것이다.
// 위치 획득 자체는 ../lib/location.js가 담당한다.
import { useEffect, useRef, useState } from "react";

import {
  accuracyText, coordText, fetchRoute, reverseGeocode, routeText, watchLocation,
} from "../lib/location";
import { kakaoJsKey, loadKakaoMaps } from "../lib/kakaoMap";

export default function LocationCard({ onLocation, destination, override, overrideLabel }) {
  const [state, setState] = useState({ position: null, accuracy: null, reason: null });
  const [address, setAddress] = useState(null);
  const [mapError, setMapError] = useState(null);
  const [route, setRoute] = useState(null);

  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const lineRef = useRef(null);
  const destMarkerRef = useRef(null);
  const routeFromRef = useRef(null);
  // 주소는 좌표가 "의미 있게" 움직였을 때만 다시 조회한다. watchPosition은 정지
  // 상태에서도 초당 여러 번 튀어서, 그대로 따라가면 카카오 API를 낭비한다.
  const lastGeocodedRef = useRef(null);

  useEffect(() => watchLocation(setState), []);

  // 화면에 보여줄 좌표. 기준 위치를 주소로 바꿨으면 그쪽이 정본이다. GPS는 계속
  // 갱신되지만, 정렬에 쓰는 좌표와 지도에 찍히는 좌표가 다르면 화면이 거짓말을 한다.
  const shown = override || state.position;

  // 상위(App)가 분석 시작 시 이 좌표를 그대로 쓴다. 같은 위치를 두 번 묻지 않는다.
  useEffect(() => { onLocation?.(state); }, [state, onLocation]);

  useEffect(() => {
    const p = shown;
    if (!p) return;
    const prev = lastGeocodedRef.current;
    // 약 30m 이상 움직였을 때만. 위도 0.0003도 ≒ 33m.
    if (prev && Math.abs(prev.lat - p.lat) < 0.0003 && Math.abs(prev.lng - p.lng) < 0.0003) return;
    lastGeocodedRef.current = p;
    let alive = true;
    reverseGeocode(p).then((a) => { if (alive) setAddress(a); });
    return () => { alive = false; };
  }, [shown]);

  // 목적지까지의 경로. 주소 조회와 같은 이유로 크게 움직였을 때만 다시 부른다.
  useEffect(() => {
    const p = shown;
    if (!p || !destination) { setRoute(null); return; }
    const prev = routeFromRef.current;
    if (prev && Math.abs(prev.lat - p.lat) < 0.001 && Math.abs(prev.lng - p.lng) < 0.001
        && prev.dest === destination.address) return;
    routeFromRef.current = { ...p, dest: destination.address };
    let alive = true;
    fetchRoute(p, destination).then((r) => { if (alive) setRoute(r); });
    return () => { alive = false; };
  }, [shown, destination]);

  // 지도 생성/갱신. 키가 없으면 loadKakaoMaps가 null을 주고 조용히 넘어간다.
  useEffect(() => {
    const p = shown;
    if (!p || !mapEl.current) return;
    let alive = true;

    loadKakaoMaps()
      .then((maps) => {
        if (!alive || !maps || !mapEl.current) return;
        const center = new maps.LatLng(p.lat, p.lng);
        if (!mapRef.current) {
          mapRef.current = new maps.Map(mapEl.current, { center, level: 4 });
          markerRef.current = new maps.Marker({ position: center, map: mapRef.current });
        } else {
          markerRef.current.setPosition(center);
        }

        // 이전 경로를 먼저 지운다. 지우지 않으면 위치가 갱신될 때마다 선이 겹쳐 쌓인다.
        lineRef.current?.setMap(null);
        destMarkerRef.current?.setMap(null);
        lineRef.current = null;
        destMarkerRef.current = null;

        if (!route) {
          mapRef.current.setCenter(center);
          return;
        }

        // 카카오는 [경도, 위도] 순으로 준다. 뒤집으면 엉뚱한 곳에 선이 그려진다.
        const points = route.path.map(([lng, lat]) => new maps.LatLng(lat, lng));
        lineRef.current = new maps.Polyline({
          map: mapRef.current, path: points,
          // 강조색 노랑. 다만 원색 #ffcd00은 밝은 지도 타일 위에서 거의 안 보여
          // 글자용 진한 노랑(styles.css의 --accent-ink)을 쓴다. 지도 API가 CSS 변수를
          // 못 받아 값을 그대로 적는다 — --accent-ink를 바꾸면 여기도 같이 고쳐야 한다.
          strokeWeight: 5, strokeColor: "#856800", strokeOpacity: 0.9, strokeStyle: "solid",
        });
        destMarkerRef.current = new maps.Marker({
          map: mapRef.current, position: points[points.length - 1],
        });

        // 출발지와 도착지가 함께 보이도록 화면을 맞춘다.
        const bounds = new maps.LatLngBounds();
        points.forEach((pt) => bounds.extend(pt));
        bounds.extend(center);
        mapRef.current.setBounds(bounds);
      })
      .catch((err) => { if (alive) setMapError(err.message); });

    return () => { alive = false; };
  }, [shown, route]);

  const showMap = Boolean(kakaoJsKey()) && shown && !mapError;

  return (
    <section className="card location-card">
      <div className="location-head">
        {/* 위 카드가 기준 위치를 정하는 곳이고 여기는 그 위치를 지도로 확인하는 곳이다.
            이름을 똑같이 두면 어느 카드를 봐야 하는지 헷갈린다. */}
        <span className="field-label">{override ? "기준 위치 지도" : "현재 위치"}</span>
        {override
          ? <span className="location-accuracy">{overrideLabel || "주소로 지정함"}</span>
          : state.accuracy != null && (
              <span className="location-accuracy">{accuracyText(state.accuracy)}</span>
            )}
      </div>

      {route && (
        <p className="location-route">
          목적지까지 <b>{routeText(route)}</b>
          {destination?.address ? ` · ${destination.address}` : ""}
        </p>
      )}

      {showMap && <div className="location-map" ref={mapEl} aria-label="현재 위치 지도" />}

      {shown ? (
        <>
          <p className="location-address">{address || coordText(shown)}</p>
          {address && <p className="location-coord">{coordText(shown)}</p>}
        </>
      ) : (
        <p className="location-address muted">{state.reason || "위치를 확인하는 중…"}</p>
      )}

      {!kakaoJsKey() && shown && (
        <p className="hint">
          지도는 카카오 JavaScript 키를 설정하면 표시됩니다.
        </p>
      )}
      {mapError && <p className="hint">{mapError} 위치는 아래 주소로 확인하세요.</p>}
      {!override && !state.position && state.reason && (
        <p className="hint">
          위치가 없으면 주변 화물을 찾을 수 없어 추천이 중단됩니다. 사진 분석은 그대로 진행됩니다.
        </p>
      )}
    </section>
  );
}
