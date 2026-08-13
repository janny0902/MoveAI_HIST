package com.moveai.backend.service;

import com.moveai.backend.entity.TerminalDistance;
import com.moveai.backend.repository.TerminalDistanceRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 터미널↔터미널 거리 행렬.
 * 목록에는 쓰지 않고, 후보 선택·최적배차·수락 직전에만 조회.
 * miss 시 카카오 1회 → DB+메모리 저장.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TerminalDistanceMatrixService {

    private final TerminalDistanceRepository repository;
    private final TerminalRegistryService terminalRegistry;
    private final KakaoNaviService kakaoNaviService;
    private final RouteMatchService routeMatchService;

    private final ConcurrentHashMap<String, Leg> mem = new ConcurrentHashMap<>();

    public record Leg(double distanceKm, double durationMin, String source) {}

    public record DetourResult(
            double baseKm,
            double viaKm,
            double extraKm,
            double extraMinutes,
            String source
    ) {}

    public Leg leg(String originCode, String destCode) {
        if (originCode == null || destCode == null) {
            return new Leg(0, 0, "missing");
        }
        String o = originCode.trim();
        String d = destCode.trim();
        if (o.equalsIgnoreCase(d)) {
            return new Leg(0, 0, "same");
        }
        String key = cacheKey(o, d);
        Leg hit = mem.get(key);
        if (hit != null) return hit;

        Optional<TerminalDistance> row = repository.findByOriginCodeAndDestCode(o, d);
        if (row.isPresent() && row.get().getDistanceKm() != null) {
            TerminalDistance r = row.get();
            Leg leg = new Leg(
                    r.getDistanceKm(),
                    r.getDurationMin() != null ? r.getDurationMin() : estimateMinutes(r.getDistanceKm()),
                    r.getSource() != null ? r.getSource() : "db"
            );
            mem.put(key, leg);
            return leg;
        }

        return fetchAndStore(o, d);
    }

    /**
     * 기사 O→D 직행 대비 O→상차→하차→D 증분.
     * 경유지가 경로에 붙을 때마다 이 합산만 하면 됨 (풀 via 카카오 호출 없음).
     */
    public DetourResult detourExtra(String driverOrigin, String pick, String drop, String driverDest) {
        Leg base = leg(driverOrigin, driverDest);
        Leg a = leg(driverOrigin, pick);
        Leg b = leg(pick, drop);
        Leg c = leg(drop, driverDest);
        double via = a.distanceKm() + b.distanceKm() + c.distanceKm();
        double extra = Math.max(0, via - base.distanceKm());
        double mins = estimateMinutes(extra);
        String src = String.join("+", a.source(), b.source(), c.source(), base.source());
        return new DetourResult(
                round1(base.distanceKm()),
                round1(via),
                round1(extra),
                Math.round(mins),
                src
        );
    }

    /** 현재 경로(waypoints 코드 순서)에 새 상·하차를 끼웠을 때 증분 */
    public DetourResult incrementalWithWaypoints(
            String driverOrigin,
            List<String> existingWaypoints,
            String newPick,
            String newDrop,
            String driverDest
    ) {
        List<String> basePath = new ArrayList<>();
        basePath.add(driverOrigin);
        if (existingWaypoints != null) basePath.addAll(existingWaypoints);
        basePath.add(driverDest);

        List<String> viaPath = new ArrayList<>();
        viaPath.add(driverOrigin);
        if (existingWaypoints != null) viaPath.addAll(existingWaypoints);
        viaPath.add(newPick);
        viaPath.add(newDrop);
        viaPath.add(driverDest);

        double baseKm = pathDistance(basePath);
        double viaKm = pathDistance(viaPath);
        double extra = Math.max(0, viaKm - baseKm);
        return new DetourResult(round1(baseKm), round1(viaKm), round1(extra), Math.round(estimateMinutes(extra)), "matrix-path");
    }

    public double pathDistance(List<String> codes) {
        if (codes == null || codes.size() < 2) return 0;
        double sum = 0;
        for (int i = 0; i < codes.size() - 1; i++) {
            sum += leg(codes.get(i), codes.get(i + 1)).distanceKm();
        }
        return sum;
    }

    /** 시연 축 등 소수 터미널 N×N warm (백그라운드 가능) */
    @Transactional
    public Map<String, Object> warmCodes(Collection<String> codes) {
        List<String> list = codes.stream().filter(Objects::nonNull).map(String::trim).distinct().toList();
        int pairs = 0;
        int kakao = 0;
        for (String a : list) {
            for (String b : list) {
                if (a.equalsIgnoreCase(b)) continue;
                Leg before = mem.get(cacheKey(a, b));
                Leg leg = leg(a, b);
                pairs++;
                if (before == null && "kakao".equals(leg.source())) kakao++;
            }
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("terminals", list.size());
        out.put("pairsComputed", pairs);
        out.put("kakaoCallsApprox", kakao);
        out.put("matrixRows", repository.count());
        return out;
    }

    private Leg fetchAndStore(String o, String d) {
        var oT = terminalRegistry.findByCode(o).orElse(null);
        var dT = terminalRegistry.findByCode(d).orElse(null);
        double dist;
        double dur;
        String source;
        if (oT != null && dT != null) {
            try {
                Map<String, Object> nav = kakaoNaviService.directionsLatLng(
                        oT.lat(), oT.lng(), oT.name(),
                        dT.lat(), dT.lng(), dT.name(),
                        List.of(), List.of());
                dist = toDouble(nav.get("distanceKm"),
                        routeMatchService.haversine(oT.lat(), oT.lng(), dT.lat(), dT.lng()));
                dur = toDouble(nav.get("durationMin"), estimateMinutes(dist));
                source = String.valueOf(nav.getOrDefault("source", "kakao"));
            } catch (Exception e) {
                log.warn("kakao leg {}→{} failed: {}", o, d, e.toString());
                dist = routeMatchService.haversine(oT.lat(), oT.lng(), dT.lat(), dT.lng());
                dur = estimateMinutes(dist);
                source = "haversine";
            }
        } else {
            dist = 0;
            dur = 0;
            source = "missing-terminal";
        }
        Leg leg = new Leg(round1(dist), Math.round(dur * 10.0) / 10.0, source);
        mem.put(cacheKey(o, d), leg);
        persist(o, d, leg);
        return leg;
    }

    private void persist(String o, String d, Leg leg) {
        try {
            TerminalDistance row = repository.findByOriginCodeAndDestCode(o, d).orElseGet(TerminalDistance::new);
            row.setOriginCode(o);
            row.setDestCode(d);
            row.setDistanceKm(leg.distanceKm());
            row.setDurationMin(leg.durationMin());
            row.setSource(leg.source());
            row.setUpdatedAt(LocalDateTime.now());
            repository.save(row);
        } catch (Exception e) {
            log.warn("persist distance {}→{}: {}", o, d, e.toString());
        }
    }

    private static String cacheKey(String o, String d) {
        return o.toUpperCase(Locale.ROOT) + ">" + d.toUpperCase(Locale.ROOT);
    }

    private static double estimateMinutes(double km) {
        return Math.round((km / 60.0) * 60.0); // ~60km/h
    }

    private static double toDouble(Object o, double def) {
        if (o instanceof Number n) return n.doubleValue();
        if (o == null) return def;
        try {
            return Double.parseDouble(String.valueOf(o));
        } catch (Exception e) {
            return def;
        }
    }

    private static double round1(double v) {
        return Math.round(v * 10.0) / 10.0;
    }
}
