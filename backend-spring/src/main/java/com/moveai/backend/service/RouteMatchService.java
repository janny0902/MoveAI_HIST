package com.moveai.backend.service;

import com.moveai.backend.station.KtxStations;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * 기사 출도착 대비 체적 출도착의 "가는 길" 유사도 / 우회 거리 추정.
 * 카카오 호출 없이 haversine + 경부축 인덱스로 빠르게 판정 (시연용).
 */
@Service
public class RouteMatchService {

    /** 경부 축 (부산→서울) — 인덱스 근접이면 유사 경로 */
    private static final List<String> GYENGBU = List.of(
            "BUSAN", "ULSAN", "GYEONGJU", "DONGDAEGU", "GIMCHEON",
            "DAEJEON", "OSONG", "CHEONAN_ASAN", "GWANGMYEONG", "SEOUL", "YONGSAN"
    );

    /** 우회 허용: 직행 대비 최대 비율 (참고용 — feed는 OdDetourService +30km) */
    public static final double MAX_DETOUR_RATIO = 1.45;
    /** 절대 우회 km (haversine 평가용) */
    public static final double MAX_EXTRA_KM = 30.0;

    public record RouteMetrics(
            boolean onRoute,
            double baseKm,
            double viaCargoKm,
            double extraKm,
            double detourRatio
    ) {}

    public RouteMetrics evaluate(
            String driverOriginCode,
            String driverDestCode,
            String cargoOriginCode,
            String cargoDestCode
    ) {
        KtxStations.Station dO = KtxStations.findByCode(driverOriginCode).orElse(null);
        KtxStations.Station dD = KtxStations.findByCode(driverDestCode).orElse(null);
        KtxStations.Station cO = KtxStations.findByCode(cargoOriginCode).orElse(null);
        KtxStations.Station cD = KtxStations.findByCode(cargoDestCode).orElse(null);
        if (dO == null || dD == null || cO == null || cD == null) {
            return new RouteMetrics(false, 0, 0, 0, 99);
        }

        double baseKm = haversine(dO.lat(), dO.lng(), dD.lat(), dD.lng());
        double viaKm = haversine(dO.lat(), dO.lng(), cO.lat(), cO.lng())
                + haversine(cO.lat(), cO.lng(), cD.lat(), cD.lng())
                + haversine(cD.lat(), cD.lng(), dD.lat(), dD.lng());
        if (baseKm < 1) baseKm = 1;
        double extra = Math.max(0, viaKm - baseKm);
        double ratio = viaKm / baseKm;

        boolean corridorOk = corridorCompatible(driverOriginCode, driverDestCode, cargoOriginCode, cargoDestCode);
        boolean detourOk = ratio <= MAX_DETOUR_RATIO || extra <= MAX_EXTRA_KM;
        boolean onRoute = corridorOk && detourOk;

        // 출도착이 기사 경로와 완전히 같아도 OK
        if (eq(driverOriginCode, cargoOriginCode) && eq(driverDestCode, cargoDestCode)) {
            onRoute = true;
            extra = Math.max(0, viaKm - baseKm);
        }

        return new RouteMetrics(
                onRoute,
                round1(baseKm),
                round1(viaKm),
                round1(extra),
                Math.round(ratio * 100.0) / 100.0
        );
    }

    private boolean corridorCompatible(String dO, String dD, String cO, String cD) {
        int ido = indexOf(dO);
        int idd = indexOf(dD);
        int ico = indexOf(cO);
        int icd = indexOf(cD);

        // 경부축 밖이면 거리 비율만으로 (evaluate의 detourOk와 AND)
        if (ido < 0 || idd < 0 || ico < 0 || icd < 0) {
            return true;
        }

        // 기사 진행 방향 정규화
        int lo = Math.min(ido, idd);
        int hi = Math.max(ido, idd);
        boolean driverUp = idd >= ido;

        // 픽업·하차가 기사 구간 근처 (±2역)
        boolean pickupIn = ico >= lo - 2 && ico <= hi + 2;
        boolean dropIn = icd >= lo - 2 && icd <= hi + 2;
        if (!pickupIn || !dropIn) return false;

        // 같은 방향 선호 (조금 어긋나도 허용)
        boolean cargoUp = icd >= ico;
        if (driverUp != cargoUp) {
            // 반대 방향이면 픽업만 구간에 있고 하차가 기사 목적 쪽이면 느슨 허용
            return Math.abs(ico - ido) <= 2;
        }
        return true;
    }

    private int indexOf(String code) {
        if (code == null) return -1;
        for (int i = 0; i < GYENGBU.size(); i++) {
            if (GYENGBU.get(i).equalsIgnoreCase(code)) return i;
        }
        return -1;
    }

    private boolean eq(String a, String b) {
        return a != null && a.equalsIgnoreCase(b);
    }

    public double haversine(double lat1, double lng1, double lat2, double lng2) {
        double R = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    private double round1(double v) {
        return Math.round(v * 10.0) / 10.0;
    }

    /** 톤수 → 대략 적재부피 (시연용) */
    public static double estimateCapacityM3(double tons) {
        if (tons <= 1.5) return 10;
        if (tons <= 3.5) return 20;
        if (tons <= 5.5) return 28;
        if (tons <= 8.5) return 40;
        if (tons <= 12) return 30.545;
        if (tons <= 18) return 60;
        return 70;
    }
}
