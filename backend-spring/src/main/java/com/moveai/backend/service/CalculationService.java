package com.moveai.backend.service;

import com.moveai.backend.entity.Truck;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class CalculationService {

    private static final double FUEL_EFFICIENCY = 3.5; // 11톤 트럭 표준 연비 (km/L)
    private static final int DIESEL_PRICE = 1500;       // 경유 가격 (L당)
    private static final double CO2_FACTOR = 0.8;      // 탄소 배출 계수 (kg/km)
    private static final ObjectMapper MAPPER = new ObjectMapper();

    /** 11톤 윙바디 표준 적재 부피 (CBM) — 2.35×9.30×2.45m 기준 가용 체적 */
    public static final double TRUCK_CAPACITY_M3_11T = 30.545;

    /** UI 톤수와 맞춘 표준 차종 프로파일 (등록 시 fill% 사전계산용) */
    public record VehicleProfile(String key, String label, double tons, double capacityM3) {}

    public static final List<VehicleProfile> STANDARD_PROFILES = List.of(
            new VehicleProfile("1t", "1톤", 1.0, 10.0),
            new VehicleProfile("2_5t", "2.5톤", 2.5, 20.0),
            new VehicleProfile("3t", "3톤", 3.0, 22.0),
            new VehicleProfile("5t", "5톤", 5.0, 28.0),
            new VehicleProfile("8t", "8톤", 8.0, 40.0),
            new VehicleProfile("11t", "11톤", 11.0, 30.545),
            new VehicleProfile("18t", "18톤", 18.0, 60.0),
            new VehicleProfile("25t", "25톤", 25.0, 70.0)
    );

    public int calculateExtraFuelCost(double extraDistanceKm) {
        return (int) ((extraDistanceKm / FUEL_EFFICIENCY) * DIESEL_PRICE);
    }

    public double calculateEsgReduction(double reducedDistanceKm) {
        return Math.round((reducedDistanceKm * CO2_FACTOR) * 100) / 100.0;
    }

    /** 선택 체적이 11톤 트럭 전체 용량에서 차지하는 비율(%) */
    public double calculateFillPercentOf11t(double volumeM3) {
        return calculateFillPercent(volumeM3, TRUCK_CAPACITY_M3_11T);
    }

    public double calculateFillPercent(double volumeM3, double capacityM3) {
        if (capacityM3 <= 0) return 0;
        return Math.round((volumeM3 / capacityM3) * 10000.0) / 100.0;
    }

    /**
     * 등록 시 1회: 표준 차종별 점유율 맵.
     * 스캔/조회 경로에서는 이 맵만 읽는다.
     */
    public Map<String, Double> calculateFillByVehicleTypes(double volumeM3) {
        Map<String, Double> out = new LinkedHashMap<>();
        for (VehicleProfile p : STANDARD_PROFILES) {
            out.put(p.key(), calculateFillPercent(volumeM3, p.capacityM3()));
        }
        return out;
    }

    public String toFillByVehicleJson(double volumeM3) {
        try {
            return MAPPER.writeValueAsString(calculateFillByVehicleTypes(volumeM3));
        } catch (Exception e) {
            return "{}";
        }
    }

    public Map<String, Double> parseFillByVehicleJson(String json) {
        if (json == null || json.isBlank()) return Map.of();
        try {
            return MAPPER.readValue(json, new TypeReference<>() {});
        } catch (Exception e) {
            return Map.of();
        }
    }

    /** 기사 차량 용량에 맞는 사전계산 fill% (없으면 volume으로 즉시 산출) */
    public double resolveFillForTruck(Double volumeM3, String fillByVehicleJson, Truck truck) {
        double vol = volumeM3 != null ? volumeM3 : 0;
        if (truck != null && truck.getCapacityM3() != null && truck.getCapacityM3() > 0) {
            // 실측 용량이 있으면 맵보다 capacity 직접 계산이 정확 (나눗셈 1회)
            return calculateFillPercent(vol, truck.getCapacityM3());
        }
        Map<String, Double> map = parseFillByVehicleJson(fillByVehicleJson);
        String key = profileKeyForTruck(truck);
        if (map.containsKey(key)) {
            return map.get(key);
        }
        double cap = capacityM3ForTruck(truck);
        return calculateFillPercent(vol, cap);
    }

    public String profileKeyForTruck(Truck truck) {
        double tons = truck != null && truck.getCapacityTons() != null ? truck.getCapacityTons() : 11.0;
        VehicleProfile best = STANDARD_PROFILES.get(4); // 11t default
        double bestDiff = Double.MAX_VALUE;
        for (VehicleProfile p : STANDARD_PROFILES) {
            double d = Math.abs(p.tons() - tons);
            if (d < bestDiff) {
                bestDiff = d;
                best = p;
            }
        }
        return best.key();
    }

    public double capacityM3ForTruck(Truck truck) {
        if (truck != null && truck.getCapacityM3() != null && truck.getCapacityM3() > 0) {
            return truck.getCapacityM3();
        }
        double tons = truck != null && truck.getCapacityTons() != null ? truck.getCapacityTons() : 11.0;
        return RouteMatchService.estimateCapacityM3(tons);
    }

    /** 현재 차량 잔여공간(%) 대비, 선택 체적이 차지하는 비율(%) */
    public double calculateFillOfRemaining(double volumeM3, double remainingPercent) {
        return calculateFillOfRemaining(volumeM3, remainingPercent, TRUCK_CAPACITY_M3_11T);
    }

    public double calculateFillOfRemaining(double volumeM3, double remainingPercent, double capacityM3) {
        double remainingM3 = capacityM3 * (remainingPercent / 100.0);
        if (remainingM3 <= 0) return 999.0;
        return Math.round((volumeM3 / remainingM3) * 10000.0) / 100.0;
    }

    /** UI/등록 미리보기용: 표준 차종 라벨 포함 맵 */
    public Map<String, Object> fillPreview(double volumeM3) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("volumeM3", Math.round(volumeM3 * 10000.0) / 10000.0);
        Map<String, Object> fills = new LinkedHashMap<>();
        for (VehicleProfile p : STANDARD_PROFILES) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("label", p.label());
            row.put("tons", p.tons());
            row.put("capacityM3", p.capacityM3());
            row.put("fillPercent", calculateFillPercent(volumeM3, p.capacityM3()));
            fills.put(p.key(), row);
        }
        out.put("fillByVehicle", fills);
        out.put("fillPercentOf11t", calculateFillPercentOf11t(volumeM3));
        out.put("profiles", STANDARD_PROFILES.stream()
                .map(p -> Map.of("key", p.key(), "label", p.label(), "tons", p.tons(), "capacityM3", p.capacityM3()))
                .toList());
        return out;
    }
}
