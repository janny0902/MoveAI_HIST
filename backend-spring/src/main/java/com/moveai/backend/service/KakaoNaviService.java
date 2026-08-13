package com.moveai.backend.service;

import com.moveai.backend.station.KtxStations;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.*;

@Slf4j
@Service
public class KakaoNaviService {

    private final RestTemplate restTemplate;

    @Value("${kakao.rest.key:}")
    private String kakaoRestKey;

    public KakaoNaviService(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    /**
     * 카카오 모빌리티 자동차 길찾기 (도로 경로 vertex)
     * origin/destination/waypoints = "lng,lat" (name 미사용 — 인코딩 이슈 방지)
     */
    public Map<String, Object> directions(
            KtxStations.Station origin,
            KtxStations.Station destination,
            List<KtxStations.Station> waypoints
    ) {
        List<KtxStations.Station> wps = waypoints == null ? List.of() : waypoints;
        return directionsGeo(
                origin.lat(), origin.lng(), origin.name(), origin.code(),
                destination.lat(), destination.lng(), destination.name(), destination.code(),
                wps.stream().map(w -> new double[]{w.lat(), w.lng()}).toList(),
                wps.stream().map(KtxStations.Station::name).toList()
        );
    }

    /** 터미널 GPS 등 임의 좌표 길찾기 (웨이포인트 = lat,lng 쌍) */
    public Map<String, Object> directionsLatLng(
            double oLat, double oLng, String oName,
            double dLat, double dLng, String dName,
            List<double[]> waypointsLatLng,
            List<String> waypointNames
    ) {
        return directionsGeo(oLat, oLng, oName, null, dLat, dLng, dName, null,
                waypointsLatLng == null ? List.of() : waypointsLatLng,
                waypointNames == null ? List.of() : waypointNames);
    }

    private Map<String, Object> directionsGeo(
            double oLat, double oLng, String oName, String oCode,
            double dLat, double dLng, String dName, String dCode,
            List<double[]> waypoints,
            List<String> waypointNames
    ) {
        Map<String, Object> result = new LinkedHashMap<>();
        List<String> routeNames = new ArrayList<>();
        routeNames.add(oName != null ? oName : "출발");
        for (String n : waypointNames) routeNames.add(n != null ? n : "경유");
        routeNames.add(dName != null ? dName : "도착");
        result.put("naviRoute", routeNames);
        result.put("origin", geoMap(oCode, oName, oLat, oLng));
        result.put("destination", geoMap(dCode, dName, dLat, dLng));
        List<Map<String, Object>> wpMaps = new ArrayList<>();
        for (int i = 0; i < waypoints.size(); i++) {
            double[] ll = waypoints.get(i);
            String nm = i < waypointNames.size() ? waypointNames.get(i) : "경유";
            wpMaps.add(geoMap(null, nm, ll[0], ll[1]));
        }
        result.put("waypoints", wpMaps);

        if (kakaoRestKey == null || kakaoRestKey.isBlank()) {
            log.warn("KAKAO_REST_KEY empty");
            result.put("source", "fallback-straight");
            result.put("message", "KAKAO_REST_KEY 없음 → 직선 경로");
            Map<String, Object> fb = fallbackPathGeo(oLat, oLng, dLat, dLng, waypoints, waypointNames);
            result.put("distanceKm", fb.get("distanceKm"));
            result.put("durationMin", fb.get("durationMin"));
            result.put("nextStep", fb.get("nextStep"));
            result.put("path", List.of());
            return result;
        }

        try {
            StringBuilder url = new StringBuilder("https://apis-navi.kakaomobility.com/v1/directions");
            url.append("?origin=").append(oLng).append(",").append(oLat);
            url.append("&destination=").append(dLng).append(",").append(dLat);
            url.append("&priority=RECOMMEND");
            url.append("&car_fuel=DIESEL");
            url.append("&car_hipass=true");
            url.append("&summary=false");

            if (!waypoints.isEmpty()) {
                // 공개 directions API 경유 최대 5개
                int limit = Math.min(5, waypoints.size());
                List<String> parts = new ArrayList<>();
                for (int i = 0; i < limit; i++) {
                    double[] ll = waypoints.get(i);
                    parts.add(ll[1] + "," + ll[0]); // lng,lat
                }
                url.append("&waypoints=").append(URLEncoder.encode(String.join("|", parts), StandardCharsets.UTF_8));
            }

            URI uri = URI.create(url.toString());
            HttpHeaders headers = new HttpHeaders();
            headers.set("Authorization", "KakaoAK " + kakaoRestKey.trim());
            headers.setAccept(List.of(MediaType.APPLICATION_JSON));

            log.info("Kakao navi request: {}", uri);
            ResponseEntity<Map> res = restTemplate.exchange(
                    uri, HttpMethod.GET, new HttpEntity<>(headers), Map.class);

            Map body = res.getBody();
            if (body == null) throw new IllegalStateException("empty body");

            if (body.get("code") != null && body.get("routes") == null) {
                throw new IllegalStateException("kakao error code=" + body.get("code")
                        + " msg=" + body.get("msg"));
            }

            List routes = (List) body.get("routes");
            if (routes == null || routes.isEmpty()) {
                throw new IllegalStateException("routes empty: " + body);
            }

            Map route0 = (Map) routes.get(0);
            Object rc = route0.get("result_code");
            if (rc != null) {
                int code = rc instanceof Number ? ((Number) rc).intValue() : Integer.parseInt(String.valueOf(rc));
                if (code != 0) {
                    throw new IllegalStateException("result_code=" + code + " " + route0.get("result_msg"));
                }
            }

            Map summary = (Map) route0.get("summary");
            double distanceM = summary != null && summary.get("distance") != null
                    ? ((Number) summary.get("distance")).doubleValue() : 0;
            double durationS = summary != null && summary.get("duration") != null
                    ? ((Number) summary.get("duration")).doubleValue() : 0;

            List<Map<String, Double>> path = extractPath(route0);
            if (path.size() < 5) {
                // 경유 포함 호출이 vertex를 못 주면 직행(무경유)으로 1회 재시도하지 않고 실패 처리
                // → 호출측 stitch가 구간별로 다시 받는다
                throw new IllegalStateException("vertex path too short: " + path.size()
                        + " result_code=" + rc + " waypoints=" + waypoints.size());
            }

            result.put("path", path);
            result.put("source", "kakao-mobility-directions");
            result.put("distanceKm", Math.round(distanceM / 100.0) / 10.0);
            result.put("durationMin", (int) Math.round(durationS / 60.0));
            result.put("nextStep", !waypointNames.isEmpty()
                    ? waypointNames.get(0) + " 경유 방면으로 이동하세요"
                    : (dName != null ? dName : "도착") + " 방면으로 이동하세요");
            log.info("Kakao navi ok: {}km, {}min, {} points", result.get("distanceKm"), result.get("durationMin"), path.size());
            return result;
        } catch (Exception e) {
            log.warn("Kakao navi failed: {}", e.toString());
            // 직선 폴백 path는 지도에 쓰면 안 됨 → 빈 path + 거리는 haversine만
            result.put("source", "fallback-error");
            result.put("message", "카카오 내비 호출 실패: " + e.getMessage());
            Map<String, Object> fb = fallbackPathGeo(oLat, oLng, dLat, dLng, waypoints, waypointNames);
            result.put("distanceKm", fb.get("distanceKm"));
            result.put("durationMin", fb.get("durationMin"));
            result.put("nextStep", fb.get("nextStep"));
            result.put("path", List.of()); // 직선 vertex 제거 — 호출측이 stitch/재시도
            return result;
        }
    }

    private Map<String, Object> geoMap(String code, String name, double lat, double lng) {
        Map<String, Object> m = new LinkedHashMap<>();
        if (code != null) m.put("code", code);
        m.put("name", name);
        m.put("lat", lat);
        m.put("lng", lng);
        return m;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Double>> extractPath(Map route0) {
        List<Map<String, Double>> path = new ArrayList<>();
        List sections = (List) route0.get("sections");
        if (sections == null) return path;
        for (Object secObj : sections) {
            Map sec = (Map) secObj;
            List roads = (List) sec.get("roads");
            if (roads == null) continue;
            for (Object roadObj : roads) {
                Map road = (Map) roadObj;
                List vertexes = (List) road.get("vertexes");
                if (vertexes == null) continue;
                for (int i = 0; i + 1 < vertexes.size(); i += 2) {
                    double lng = ((Number) vertexes.get(i)).doubleValue();
                    double lat = ((Number) vertexes.get(i + 1)).doubleValue();
                    Map<String, Double> p = new LinkedHashMap<>();
                    p.put("lat", lat);
                    p.put("lng", lng);
                    path.add(p);
                }
            }
        }
        return path;
    }

    private Map<String, Object> fallbackPathGeo(
            double oLat, double oLng,
            double dLat, double dLng,
            List<double[]> waypoints,
            List<String> waypointNames
    ) {
        List<Map<String, Double>> path = new ArrayList<>();
        path.add(point(oLat, oLng));
        if (waypoints != null) {
            for (double[] ll : waypoints) path.add(point(ll[0], ll[1]));
        }
        path.add(point(dLat, dLng));

        double distKm = 0;
        for (int i = 1; i < path.size(); i++) {
            distKm += haversine(
                    path.get(i - 1).get("lat"), path.get(i - 1).get("lng"),
                    path.get(i).get("lat"), path.get(i).get("lng"));
        }

        Map<String, Object> m = new LinkedHashMap<>();
        m.put("path", path);
        m.put("distanceKm", Math.round(distKm * 10.0) / 10.0);
        m.put("durationMin", (int) Math.round(distKm / 80.0 * 60));
        m.put("nextStep", waypointNames != null && !waypointNames.isEmpty()
                ? waypointNames.get(0) + " 경유 방면으로 이동하세요"
                : "도착 방면으로 이동하세요");
        return m;
    }

    private Map<String, Double> point(double lat, double lng) {
        Map<String, Double> p = new LinkedHashMap<>();
        p.put("lat", lat);
        p.put("lng", lng);
        return p;
    }

    private double haversine(double lat1, double lng1, double lat2, double lng2) {
        double R = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }
}
