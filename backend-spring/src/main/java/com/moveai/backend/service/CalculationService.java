package com.moveai.backend.service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class CalculationService {

    public record VehicleProfile(String key, String label, double tons, double capacityM3) {}

    public static final List<VehicleProfile> STANDARD_PROFILES = List.of(
            new VehicleProfile("1t", "1톤", 1.0, 10.0),
            new VehicleProfile("2_5t", "2.5톤", 2.5, 20.0),
            new VehicleProfile("3t", "3톤", 3.0, 22.0),
            new VehicleProfile("5t", "5톤", 5.0, 28.0),
            new VehicleProfile("8t", "8톤", 8.0, 40.0),
            new VehicleProfile("11t", "11톤", 11.0, 50.0),
            new VehicleProfile("18t", "18톤", 18.0, 60.0),
            new VehicleProfile("25t", "25톤", 25.0, 70.0)
    );

    public double calculateFillPercent(double volumeM3, double capacityM3) {
        if (capacityM3 <= 0) return 0;
        return Math.round((volumeM3 / capacityM3) * 10000.0) / 100.0;
    }

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
        out.put("fillPercentOf11t", calculateFillPercent(volumeM3, 50.0));
        return out;
    }
}
