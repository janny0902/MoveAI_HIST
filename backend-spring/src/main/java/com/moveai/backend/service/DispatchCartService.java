package com.moveai.backend.service;

import com.moveai.backend.entity.CargoOdGroup;
import com.moveai.backend.entity.Truck;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * 복화 장바구니: 담은 OD들을 기사 O→D 축에 맞춰 경유지로 합치고
 * 직행 대비 총거리·증분을 계산한다.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DispatchCartService {

    /** 경부 축 순서 (남→북). 정렬·방향 판별용 */
    private static final List<String> CORRIDOR = List.of(
            "200", "201", "300", "308", "500", "501", "503", "514", "001", "008"
    );

    private final CargoOdGroupService cargoOdGroupService;
    private final TerminalRegistryService terminalRegistry;
    private final TerminalDistanceMatrixService distanceMatrix;
    private final CalculationService calculationService;
    private final KakaoNaviService kakaoNaviService;

    public record CartLeg(Long odGroupId, Long requestId, String pickCode, String dropCode,
                          String pickName, String dropName, int boxes, double fillPercent, int fee) {}

    public Map<String, Object> preview(Truck truck, List<Long> odGroupIds) {
        String origin = truck.getOriginCode() != null ? truck.getOriginCode().trim() : "200";
        String dest = truck.getDestinationCode() != null ? truck.getDestinationCode().trim() : "001";

        List<CartLeg> legs = new ArrayList<>();
        double fillSum = 0;
        int feeSum = 0;
        int boxSum = 0;
        for (Long gid : odGroupIds) {
            if (gid == null) continue;
            CargoOdGroup g = cargoOdGroupService.findGroup(gid).orElse(null);
            if (g == null) continue;
            String pick = nz(g.getOriginTerminalCode(), g.getOriginStationCode());
            String drop = nz(g.getDestinationTerminalCode(), g.getDestinationStationCode());
            if (pick.isBlank() || drop.isBlank()) continue;
            double fill = calculationService.resolveFillForTruck(g.getVolumeM3(), g.getFillByVehicleJson(), truck);
            int fee = g.getFreightKrw() != null ? g.getFreightKrw() : 0;
            int boxes = g.getBoxCount() != null ? g.getBoxCount() : (g.getWaybillCount() != null ? g.getWaybillCount() : 0);
            legs.add(new CartLeg(
                    g.getId(),
                    g.getCargoRequestId(),
                    pick, drop,
                    nameOf(pick, g.getOriginTerminalName()),
                    nameOf(drop, g.getDestinationTerminalName()),
                    boxes, fill, fee
            ));
            fillSum += fill;
            feeSum += fee;
            boxSum += boxes;
        }

        // 장바구니 OD를 기사 진행 방향 상차 순으로 정렬 (부산→대구→부산 방지)
        legs.sort((a, b) -> compareAlongDriver(a.pickCode(), b.pickCode(), origin, dest));

        List<String> routeCodes = buildOrderedRoute(origin, dest, legs);
        double baseKmMatrix = distanceMatrix.pathDistance(List.of(origin, dest));
        double totalKmMatrix = distanceMatrix.pathDistance(routeCodes);

        List<Map<String, Object>> stops = new ArrayList<>();
        List<String> routeNames = new ArrayList<>();
        List<double[]> midLatLng = new ArrayList<>();
        List<String> midNames = new ArrayList<>();
        double oLat = 0, oLng = 0, dLat = 0, dLng = 0;
        String oName = origin, dName = dest;

        for (int i = 0; i < routeCodes.size(); i++) {
            String code = routeCodes.get(i);
            ResolvedStop rs = resolveStop(code, legs);
            String role = i == 0 ? "출발" : (i == routeCodes.size() - 1 ? "도착" : "경유");
            Map<String, Object> stop = new LinkedHashMap<>();
            stop.put("code", code);
            stop.put("name", rs.name());
            stop.put("role", role);
            stop.put("lat", rs.lat());
            stop.put("lng", rs.lng());
            stops.add(stop);
            routeNames.add(rs.name());
            if (i == 0) {
                oLat = rs.lat();
                oLng = rs.lng();
                oName = rs.name();
            } else if (i == routeCodes.size() - 1) {
                dLat = rs.lat();
                dLng = rs.lng();
                dName = rs.name();
            } else if (rs.lat() != 0 || rs.lng() != 0) {
                midLatLng.add(new double[]{rs.lat(), rs.lng()});
                midNames.add(rs.name());
            }
        }

        // GPS 유효한 경유지만 내비에 전달 (0,0·한국 밖 → 수만 km 경로/지도 깨짐 방지)
        List<double[]> midOk = new ArrayList<>();
        List<String> midNamesOk = new ArrayList<>();
        for (int i = 0; i < midLatLng.size(); i++) {
            double[] ll = midLatLng.get(i);
            if (isKoreaGps(ll[0], ll[1])) {
                midOk.add(ll);
                midNamesOk.add(i < midNames.size() ? midNames.get(i) : "경유");
            }
        }

        // 배차 지도는 반드시 도로 vertex. 다구간 일괄 호출은 실패·직선 폴백이 잦아
        // 스톱 구간마다 카카오 길찾기를 이어 붙이는 방식을 우선한다.
        List<Map<String, Object>> path = new ArrayList<>();
        double totalKm = totalKmMatrix > 0 ? totalKmMatrix : 0;
        double baseKm = baseKmMatrix > 0 ? baseKmMatrix : 0;
        Integer durationMin = null;
        String pathSource = "matrix";

        StitchedRoute stitched = stitchRoadPath(stops);
        if (stitched.path().size() >= 5) {
            path = stitched.path();
            if (stitched.distanceKm() > 0) totalKm = stitched.distanceKm();
            if (stitched.durationMin() != null) durationMin = stitched.durationMin();
            pathSource = "kakao-stitched";
        }

        boolean originOk = isKoreaGps(oLat, oLng);
        boolean destOk = isKoreaGps(dLat, dLng);
        // 스티치가 약할 때만 O→D(+경유≤5) 일괄 재시도
        if (path.size() < 5 && originOk && destOk) {
            try {
                List<double[]> midCap = midOk.size() > 5 ? midOk.subList(0, 5) : midOk;
                List<String> nameCap = midNamesOk.size() > 5 ? midNamesOk.subList(0, 5) : midNamesOk;
                Map<String, Object> navi = kakaoNaviService.directionsLatLng(
                        oLat, oLng, oName, dLat, dLng, dName, midCap, nameCap);
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> naviPath = (List<Map<String, Object>>) navi.get("path");
                double naviKm = navi.get("distanceKm") instanceof Number n ? n.doubleValue() : -1;
                String src = String.valueOf(navi.getOrDefault("source", ""));
                if (isRoadPath(src, naviPath, naviKm, totalKmMatrix)) {
                    List<Map<String, Object>> filtered = filterKoreaPath(naviPath);
                    if (filtered.size() >= 5) {
                        path = filtered;
                        totalKm = naviKm;
                        if (navi.get("durationMin") instanceof Number n) {
                            durationMin = (int) Math.round(n.doubleValue());
                        }
                        pathSource = src.isBlank() ? "kakao-navi" : src;
                    }
                }
            } catch (Exception e) {
                // stitch 결과 유지
            }
        }

        // 직행 baseKm · 직행 시간 (도로)
        Integer baseMinutes = null;
        if (originOk && destOk) {
            try {
                Map<String, Object> baseNavi = kakaoNaviService.directionsLatLng(
                        oLat, oLng, oName, dLat, dLng, dName, List.of(), List.of());
                String bsrc = String.valueOf(baseNavi.getOrDefault("source", ""));
                if (baseNavi.get("distanceKm") instanceof Number n) {
                    double bk = n.doubleValue();
                    if (bk > 0 && bk < 1500 && !bsrc.contains("fallback")) baseKm = bk;
                }
                if (baseNavi.get("durationMin") instanceof Number n) {
                    int bm = (int) Math.round(n.doubleValue());
                    if (bm > 0 && !bsrc.contains("fallback")) baseMinutes = bm;
                }
            } catch (Exception ignored) { /* matrix base 유지 */ }
        }

        if (path.isEmpty()) {
            for (Map<String, Object> s : stops) {
                Object la = s.get("lat");
                Object ln = s.get("lng");
                if (!(la instanceof Number) || !(ln instanceof Number)) continue;
                double lat = ((Number) la).doubleValue();
                double lng = ((Number) ln).doubleValue();
                if (!isKoreaGps(lat, lng)) continue;
                path.add(Map.of("lat", lat, "lng", lng));
            }
            if (!path.isEmpty()) pathSource = "stops-only";
            if (totalKmMatrix > 0) totalKm = totalKmMatrix;
        }

        if (baseKm <= 0 && baseKmMatrix > 0) baseKm = baseKmMatrix;
        if (totalKm <= 0 && totalKmMatrix > 0) totalKm = totalKmMatrix;

        double extraKm = Math.max(0, totalKm - baseKm);
        int totalMinutes = durationMin != null
                ? Math.max(1, durationMin)
                : (int) Math.round(Math.max(1, totalKm / 70.0 * 60));
        int baseMin = baseMinutes != null
                ? Math.max(1, baseMinutes)
                : (baseKm > 0 ? (int) Math.round(Math.max(1, baseKm / 70.0 * 60)) : 0);
        int extraMinutes = Math.max(0, totalMinutes - baseMin);
        int fuel = calculationService.calculateExtraFuelCost(extraKm);

        // 건별 증분: 직전 장바구니 대비 (행렬 — 빠른 미리보기)
        List<Map<String, Object>> itemRows = new ArrayList<>();
        List<Long> progressive = new ArrayList<>();
        double prevVia = baseKmMatrix;
        for (CartLeg leg : legs) {
            progressive.add(leg.odGroupId());
            List<CartLeg> partial = legs.subList(0, progressive.size());
            List<String> codes = buildOrderedRoute(origin, dest, partial);
            double via = distanceMatrix.pathDistance(codes);
            double added = Math.max(0, via - prevVia);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("odGroupId", leg.odGroupId());
            row.put("requestId", leg.requestId());
            row.put("origin", leg.pickName());
            row.put("destination", leg.dropName());
            row.put("originCode", leg.pickCode());
            row.put("destinationCode", leg.dropCode());
            row.put("boxCount", leg.boxes());
            row.put("fillPercent", round1(leg.fillPercent()));
            row.put("proposedFee", leg.fee());
            row.put("addedKm", round1(added));
            row.put("totalKmAfter", round1(via));
            itemRows.add(row);
            prevVia = via;
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("originCode", origin);
        out.put("destinationCode", dest);
        out.put("baseKm", round1(baseKm));
        out.put("totalKm", round1(totalKm));
        out.put("extraKm", round1(extraKm));
        out.put("durationMin", totalMinutes);
        out.put("baseMinutes", baseMin);
        out.put("extraMinutes", extraMinutes);
        out.put("extraFuelCost", fuel);
        out.put("netProfit", feeSum - fuel);
        out.put("fillPercentSum", round1(fillSum));
        out.put("boxCountSum", boxSum);
        out.put("itemCount", legs.size());
        out.put("routeCodes", routeCodes);
        out.put("routeNames", routeNames);
        out.put("routeLabel", String.join(" → ", routeNames));
        out.put("stops", stops);
        out.put("path", path);
        out.put("pathSource", pathSource);
        out.put("items", itemRows);
        out.put("requestIds", legs.stream().map(CartLeg::requestId).filter(Objects::nonNull).toList());
        return out;
    }

    /** 운행 중 경유 추가 후 도로선만 다시 이음. */
    public Map<String, Object> restitchFromStops(List<Map<String, Object>> stops) {
        List<Map<String, Object>> list = stops != null ? stops : List.of();
        StitchedRoute stitched = stitchRoadPath(list);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("path", stitched.path());
        out.put("totalKm", stitched.distanceKm());
        out.put("durationMin", stitched.durationMin());
        out.put("stops", list);
        out.put("pathSource", stitched.path().isEmpty() ? "none" : "kakao-stitched");
        return out;
    }

    private record ResolvedStop(String name, double lat, double lng) {}

    private ResolvedStop resolveStop(String code, List<CartLeg> legs) {
        var t = terminalRegistry.findByCode(code).orElse(null);
        String name = t != null ? t.name() : code;
        double lat = t != null ? t.lat() : 0;
        double lng = t != null ? t.lng() : 0;
        if ((lat == 0 || lng == 0) && !legs.isEmpty()) {
            for (CartLeg leg : legs) {
                if (code.equalsIgnoreCase(leg.pickCode()) || code.equalsIgnoreCase(leg.dropCode())) {
                    CargoOdGroup g = cargoOdGroupService.findGroup(leg.odGroupId()).orElse(null);
                    if (g == null) continue;
                    if (code.equalsIgnoreCase(leg.pickCode()) && g.getOriginLat() != null) {
                        lat = g.getOriginLat();
                        lng = g.getOriginLng();
                        if (g.getOriginTerminalName() != null) name = g.getOriginTerminalName();
                    } else if (code.equalsIgnoreCase(leg.dropCode()) && g.getDestinationLat() != null) {
                        lat = g.getDestinationLat();
                        lng = g.getDestinationLng();
                        if (g.getDestinationTerminalName() != null) name = g.getDestinationTerminalName();
                    }
                }
            }
        }
        return new ResolvedStop(nameOf(code, name), lat, lng);
    }

    /**
     * 기사 진행 방향으로 터미널을 정렬해 O → (경유) → D 경로를 만든다.
     * 같은 터미널 연속은 합친다.
     */
    List<String> buildOrderedRoute(String origin, String dest, List<CartLeg> legs) {
        boolean northbound = corridorIndex(dest) >= corridorIndex(origin);
        Set<String> mids = new LinkedHashSet<>();
        for (CartLeg leg : legs) {
            if (!leg.pickCode().equalsIgnoreCase(origin) && !leg.pickCode().equalsIgnoreCase(dest)) {
                mids.add(leg.pickCode());
            }
            if (!leg.dropCode().equalsIgnoreCase(origin) && !leg.dropCode().equalsIgnoreCase(dest)) {
                mids.add(leg.dropCode());
            }
        }
        List<String> sorted = new ArrayList<>(mids);
        sorted.sort((a, b) -> {
            int cmp = Integer.compare(corridorIndex(a), corridorIndex(b));
            return northbound ? cmp : -cmp;
        });

        List<String> route = new ArrayList<>();
        route.add(origin);
        for (String c : sorted) {
            if (!c.equalsIgnoreCase(route.get(route.size() - 1))) {
                route.add(c);
            }
        }
        if (!dest.equalsIgnoreCase(route.get(route.size() - 1))) {
            route.add(dest);
        }
        return route;
    }

    /**
     * 기사 O→D 진행 방향으로 터미널 코드 비교.
     * 1차: 경부 축 인덱스, 2차: 위도(북상 시 남쪽 상차 먼저).
     */
    public int compareAlongDriver(String codeA, String codeB, String origin, String dest) {
        boolean northbound = corridorIndex(dest) >= corridorIndex(origin);
        int cmp = Integer.compare(corridorIndex(codeA), corridorIndex(codeB));
        if (cmp != 0) return northbound ? cmp : -cmp;
        double latA = latOf(codeA);
        double latB = latOf(codeB);
        int latCmp = Double.compare(latA, latB);
        if (latCmp != 0) return northbound ? latCmp : -latCmp;
        return String.valueOf(codeA).compareToIgnoreCase(String.valueOf(codeB));
    }

    private double latOf(String code) {
        if (code == null || code.isBlank()) return 0;
        return terminalRegistry.findByCode(code.trim())
                .map(TerminalRegistryService.Terminal::lat)
                .orElse(0.0);
    }

    private static int corridorIndex(String code) {
        if (code == null) return 50;
        String c = code.trim();
        int i = CORRIDOR.indexOf(c);
        if (i >= 0) return i;
        try {
            int n = Integer.parseInt(c);
            if (n <= 50) return 90;
            if (n >= 200 && n < 300) return 0;
            if (n >= 300 && n < 400) return 20;
            if (n >= 500 && n < 600) return 40;
            return 50;
        } catch (Exception e) {
            return 50;
        }
    }

    private String nameOf(String code, String fallback) {
        return terminalRegistry.findByCode(code).map(TerminalRegistryService.Terminal::name)
                .orElse(fallback != null ? fallback : code);
    }

    private static String nz(String a, String b) {
        if (a != null && !a.isBlank()) return a.trim();
        if (b != null && !b.isBlank()) return b.trim();
        return "";
    }

    private static double round1(double v) {
        return Math.round(v * 10.0) / 10.0;
    }

    /** 한반도 대략 범위 (가상터미널 0,0·해외 GPS 제외) */
    private static boolean isKoreaGps(double lat, double lng) {
        return lat >= 33.0 && lat <= 39.5 && lng >= 124.0 && lng <= 132.5;
    }

    /** 실제 도로 vertex 경로인지 (직선 폴백·이상 거리 제외) */
    private static boolean isRoadPath(String source, List<?> path, double naviKm, double matrixKm) {
        if (path == null || path.size() < 5) return false;
        if (source != null && source.contains("fallback")) return false;
        if (naviKm <= 0 || naviKm >= 2000) return false;
        if (matrixKm > 0 && naviKm > Math.max(900, matrixKm * 3 + 120)) return false;
        return true;
    }

    private record StitchedRoute(List<Map<String, Object>> path, double distanceKm, Integer durationMin) {}

    /**
     * 스톱 간 카카오 길찾기를 이어 붙여 도로 폴리라인 생성.
     * 다구간 일괄 호출(직선 폴백) 대신 배차·운행 지도의 기본 경로 소스.
     */
    @SuppressWarnings("unchecked")
    private StitchedRoute stitchRoadPath(List<Map<String, Object>> stops) {
        List<double[]> pts = new ArrayList<>();
        List<String> names = new ArrayList<>();
        for (Map<String, Object> s : stops) {
            Object la = s.get("lat");
            Object ln = s.get("lng");
            if (!(la instanceof Number) || !(ln instanceof Number)) continue;
            double lat = ((Number) la).doubleValue();
            double lng = ((Number) ln).doubleValue();
            if (!isKoreaGps(lat, lng)) continue;
            // 연속 동일 좌표 스킵
            if (!pts.isEmpty()) {
                double[] prev = pts.get(pts.size() - 1);
                if (Math.abs(prev[0] - lat) < 1e-5 && Math.abs(prev[1] - lng) < 1e-5) continue;
            }
            pts.add(new double[]{lat, lng});
            names.add(String.valueOf(s.getOrDefault("name", "경유")));
        }
        if (pts.size() < 2) return new StitchedRoute(List.of(), 0, null);

        List<Map<String, Object>> out = new ArrayList<>();
        double sumKm = 0;
        int sumMin = 0;
        int roadLegs = 0;
        for (int i = 0; i < pts.size() - 1; i++) {
            double[] a = pts.get(i);
            double[] b = pts.get(i + 1);
            try {
                Map<String, Object> leg = kakaoNaviService.directionsLatLng(
                        a[0], a[1], names.get(i), b[0], b[1], names.get(i + 1), List.of(), List.of());
                String src = String.valueOf(leg.getOrDefault("source", ""));
                List<Map<String, Object>> legPath = (List<Map<String, Object>>) leg.get("path");
                List<Map<String, Object>> filtered = filterKoreaPath(legPath != null ? legPath : List.of());
                // 직선 폴백·과소 vertex는 도로로 인정하지 않음
                if (src.contains("fallback") || filtered.size() < 5) {
                    log.warn("cart stitch leg {}→{} not road (src={}, pts={})",
                            names.get(i), names.get(i + 1), src, filtered.size());
                    continue;
                }
                roadLegs++;
                int start = out.isEmpty() ? 0 : 1;
                for (int j = start; j < filtered.size(); j++) out.add(filtered.get(j));
                if (leg.get("distanceKm") instanceof Number n) sumKm += n.doubleValue();
                if (leg.get("durationMin") instanceof Number n) sumMin += (int) Math.round(n.doubleValue());
            } catch (Exception e) {
                log.warn("cart stitch leg failed {}→{}: {}", names.get(i), names.get(i + 1), e.toString());
            }
        }
        if (roadLegs == 0 || out.size() < 5) {
            return new StitchedRoute(List.of(), 0, null);
        }
        log.info("cart stitch ok: {} legs, {} pts, {}km", roadLegs, out.size(), round1(sumKm));
        return new StitchedRoute(out, round1(sumKm), sumMin > 0 ? sumMin : null);
    }

    private static List<Map<String, Object>> filterKoreaPath(List<Map<String, Object>> raw) {
        List<Map<String, Object>> out = new ArrayList<>();
        if (raw == null) return out;
        for (Map<String, Object> p : raw) {
            Object la = p.get("lat");
            Object ln = p.get("lng");
            if (!(la instanceof Number) || !(ln instanceof Number)) continue;
            double lat = ((Number) la).doubleValue();
            double lng = ((Number) ln).doubleValue();
            if (!isKoreaGps(lat, lng)) continue;
            out.add(p);
        }
        return out;
    }
}
