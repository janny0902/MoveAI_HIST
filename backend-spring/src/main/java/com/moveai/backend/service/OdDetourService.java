package com.moveai.backend.service;

import com.moveai.backend.entity.CargoOdGroup;
import com.moveai.backend.entity.Truck;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * 복화 후보: 목록은 거리 없이 페이징.
 * 도로 증분은 터미널 거리 행렬로만 산출 (풀 via 카카오 호출 없음).
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class OdDetourService {

    public static final double MAX_EXTRA_KM = 30.0;
    public static final double PREFILTER_EXTRA_KM = 45.0;
    public static final int PAGE_SIZE = 5;

    private final TerminalRegistryService terminalRegistry;
    private final TerminalDistanceMatrixService distanceMatrix;
    private final CalculationService calculationService;

    public record Candidate(
            CargoOdGroup group,
            double pickupDistKm,
            double straightExtraKm,
            Double roadExtraKm,
            Double extraMinutes,
            String distanceSource,
            double fillPercent
    ) {}

    public record PageResult(
            List<Candidate> pageItems,
            int page,
            int pageSize,
            boolean hasMore,
            int candidateCount,
            double baseKm,
            String baseSource
    ) {}

    public PageResult pageForTruck(Truck truck, List<CargoOdGroup> groups, int page, double remPercent) {
        return pageForTruck(truck, groups, page, remPercent, null, false);
    }

    public PageResult pageForTruck(
            Truck truck,
            List<CargoOdGroup> groups,
            int page,
            double remPercent,
            String originTerminalCode
    ) {
        return pageForTruck(truck, groups, page, remPercent, originTerminalCode, false);
    }

    /**
     * @param computeRoadExtra true면 페이지 후보에 대해 행렬 기반 증분 계산 (최적배차용).
     *                         false면 거리 생략(목록 속도).
     */
    public PageResult pageForTruck(
            Truck truck,
            List<CargoOdGroup> groups,
            int page,
            double remPercent,
            String originTerminalCode,
            boolean computeRoadExtra
    ) {
        List<CargoOdGroup> filtered = groups;
        if (originTerminalCode != null && !originTerminalCode.isBlank()) {
            String code = originTerminalCode.trim();
            filtered = groups.stream()
                    .filter(g -> code.equalsIgnoreCase(g.getOriginTerminalCode())
                            || code.equalsIgnoreCase(g.getOriginStationCode()))
                    .toList();
        }
        return pageForTruckInternal(truck, filtered, page, remPercent, computeRoadExtra);
    }

    private PageResult pageForTruckInternal(
            Truck truck,
            List<CargoOdGroup> groups,
            int page,
            double remPercent,
            boolean computeRoadExtra
    ) {
        String oCode = resolveDriverOriginCode(truck);
        String dCode = resolveDriverDestCode(truck);
        TerminalRegistryService.Terminal dO = terminalRegistry.findByCode(oCode).orElse(null);
        TerminalRegistryService.Terminal dD = terminalRegistry.findByCode(dCode).orElse(null);
        if (dO == null) {
            dO = resolveTruckTerminal(oCode, truck.getOriginName(), truck.getCurrentLat(), truck.getCurrentLng());
        }
        if (dD == null) {
            dD = resolveTruckTerminal(dCode, truck.getDestinationName(), 37.57, 127.0);
        }
        if (dO == null || dD == null) {
            return new PageResult(List.of(), page, PAGE_SIZE, false, 0, 0, "missing-terminals");
        }

        double baseKm = 0;
        String baseSource = "skip";
        if (computeRoadExtra) {
            var baseLeg = distanceMatrix.leg(dO.code(), dD.code());
            baseKm = baseLeg.distanceKm();
            baseSource = baseLeg.source();
        }

        List<Candidate> prelim = new ArrayList<>();
        for (CargoOdGroup g : groups) {
            if (g.getWaybillCount() == null || g.getWaybillCount() <= 0) continue;
            double need = calculationService.resolveFillForTruck(g.getVolumeM3(), g.getFillByVehicleJson(), truck);
            if (need <= 0 && g.getFillPercentOf11t() != null) need = g.getFillPercentOf11t();
            if (remPercent + 0.01 < need) continue;

            double pickupDist = 0;
            double straightExtra = 0;
            double[] pick = resolveGroupOrigin(g);
            double[] drop = resolveGroupDest(g);
            if (pick != null && drop != null && computeRoadExtra) {
                // 직선은 정렬용 힌트만 (카카오 없음)
                pickupDist = haversineApprox(dO.lat(), dO.lng(), pick[0], pick[1]);
            }
            prelim.add(new Candidate(g, round1(pickupDist), round1(straightExtra), null, null, "prefilter", need));
        }

        if (computeRoadExtra) {
            prelim.sort(Comparator.comparingDouble(Candidate::pickupDistKm));
        } else {
            prelim.sort(Comparator.comparingLong(c -> c.group().getId() != null ? c.group().getId() : 0L));
        }

        int needStart = Math.max(0, page) * PAGE_SIZE;
        int toIdx = Math.min(needStart + PAGE_SIZE, prelim.size());
        int fromIdx = Math.min(needStart, prelim.size());
        List<Candidate> pageItems = new ArrayList<>();
        if (fromIdx < toIdx) {
            for (Candidate c : prelim.subList(fromIdx, toIdx)) {
                if (!computeRoadExtra) {
                    pageItems.add(c);
                    continue;
                }
                pageItems.add(attachMatrixExtra(dO.code(), dD.code(), c));
            }
        }
        boolean hasMore = toIdx < prelim.size();
        return new PageResult(pageItems, page, PAGE_SIZE, hasMore, prelim.size(), round1(baseKm), baseSource);
    }

    /** 후보 1건 — 수락/상세 직전 온디맨드 */
    public Candidate estimateOne(Truck truck, CargoOdGroup group) {
        String oCode = resolveDriverOriginCode(truck);
        String dCode = resolveDriverDestCode(truck);
        double need = calculationService.resolveFillForTruck(group.getVolumeM3(), group.getFillByVehicleJson(), truck);
        Candidate base = new Candidate(group, 0, 0, null, null, "pending", need);
        if (oCode == null || dCode == null) {
            return new Candidate(group, 0, 0, 0.0, 0.0, "missing-driver-od", need);
        }
        String pick = group.getOriginTerminalCode();
        String drop = group.getDestinationTerminalCode();
        if (pick == null || drop == null) {
            return new Candidate(group, 0, 0, 0.0, 0.0, "no-codes", need);
        }
        return attachMatrixExtra(oCode, dCode, base);
    }

    /** 기사 출발 터미널 코드 (미설정 시 GPS 최근접) */
    private String resolveDriverOriginCode(Truck truck) {
        if (truck.getOriginCode() != null && !truck.getOriginCode().isBlank()) {
            String c = truck.getOriginCode().trim();
            if (terminalRegistry.findByCode(c).isPresent()) return c;
        }
        Double lat = truck.getCurrentLat();
        Double lng = truck.getCurrentLng();
        if (lat != null && lng != null && lat != 0 && lng != 0) {
            return nearestTerminalCode(lat, lng, "200");
        }
        return "200";
    }

    private String resolveDriverDestCode(Truck truck) {
        if (truck.getDestinationCode() != null && !truck.getDestinationCode().isBlank()) {
            String c = truck.getDestinationCode().trim();
            if (terminalRegistry.findByCode(c).isPresent()) return c;
        }
        String origin = resolveDriverOriginCode(truck);
        // 출발이 부산권이면 기본 도착 서울, 그 외는 부산
        if (origin.startsWith("2")) return "001";
        return "200";
    }

    private String nearestTerminalCode(double lat, double lng, String fallback) {
        TerminalRegistryService.Terminal best = null;
        double bestD = Double.MAX_VALUE;
        for (TerminalRegistryService.Terminal t : terminalRegistry.listTerminals()) {
            double d = haversineApprox(lat, lng, t.lat(), t.lng());
            if (d < bestD) {
                bestD = d;
                best = t;
            }
        }
        return best != null ? best.code() : fallback;
    }

    private Candidate attachMatrixExtra(String driverO, String driverD, Candidate c) {
        String pick = c.group().getOriginTerminalCode();
        String drop = c.group().getDestinationTerminalCode();
        if (pick == null || drop == null) {
            return new Candidate(c.group(), c.pickupDistKm(), c.straightExtraKm(), 0.0, 0.0, "no-codes", c.fillPercent());
        }
        try {
            var det = distanceMatrix.detourExtra(driverO, pick, drop, driverD);
            return new Candidate(
                    c.group(),
                    c.pickupDistKm(),
                    c.straightExtraKm(),
                    det.extraKm(),
                    det.extraMinutes(),
                    "matrix:" + det.source(),
                    c.fillPercent()
            );
        } catch (Exception e) {
            log.warn("matrix detour failed: {}", e.toString());
            return new Candidate(c.group(), c.pickupDistKm(), c.straightExtraKm(), 0.0, 0.0, "error", c.fillPercent());
        }
    }

    private TerminalRegistryService.Terminal resolveTruckTerminal(String code, String name, Double lat, Double lng) {
        if (code != null) {
            Optional<TerminalRegistryService.Terminal> t = terminalRegistry.findByCode(code);
            if (t.isPresent()) return t.get();
        }
        if (lat != null && lng != null && lat != 0 && lng != 0) {
            return new TerminalRegistryService.Terminal(
                    code != null ? code : "GPS",
                    name != null ? name : "현재위치",
                    "",
                    lat, lng
            );
        }
        return null;
    }

    private double[] resolveGroupOrigin(CargoOdGroup g) {
        if (g.getOriginLat() != null && g.getOriginLng() != null
                && g.getOriginLat() != 0 && g.getOriginLng() != 0) {
            return new double[]{g.getOriginLat(), g.getOriginLng()};
        }
        return terminalRegistry.findByCode(g.getOriginTerminalCode())
                .map(t -> new double[]{t.lat(), t.lng()})
                .orElse(null);
    }

    private double[] resolveGroupDest(CargoOdGroup g) {
        if (g.getDestinationLat() != null && g.getDestinationLng() != null
                && g.getDestinationLat() != 0 && g.getDestinationLng() != 0) {
            return new double[]{g.getDestinationLat(), g.getDestinationLng()};
        }
        return terminalRegistry.findByCode(g.getDestinationTerminalCode())
                .map(t -> new double[]{t.lat(), t.lng()})
                .orElse(null);
    }

    /** 시연 축: 서울 동부·강남, 부산 강서·사상은 같은 도착 권역. */
    public static String destRegion(String codeOrName) {
        if (codeOrName == null || codeOrName.isBlank()) return "";
        String c = codeOrName.trim();
        return switch (c) {
            case "001", "008" -> "SEOUL";
            case "200", "201" -> "BUSAN";
            default -> {
                String u = c.toUpperCase(Locale.ROOT);
                if (c.contains("서울") || u.contains("SEOUL")) yield "SEOUL";
                if (c.contains("부산") || u.contains("BUSAN")) yield "BUSAN";
                yield u;
            }
        };
    }

    public static boolean sameDestRegion(String a, String b) {
        if (a == null || b == null) return false;
        if (a.trim().equalsIgnoreCase(b.trim())) return true;
        String ra = destRegion(a);
        String rb = destRegion(b);
        return !ra.isBlank() && ra.equals(rb);
    }

    public static double haversineKm(double lat1, double lng1, double lat2, double lng2) {
        double R = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    private static double haversineApprox(double lat1, double lng1, double lat2, double lng2) {
        return haversineKm(lat1, lng1, lat2, lng2);
    }

    private static double round1(double v) {
        return Math.round(v * 10.0) / 10.0;
    }
}
