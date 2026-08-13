package com.moveai.backend.service;

import com.moveai.backend.entity.CargoRequest;
import com.moveai.backend.repository.CargoRequestRepository;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VolumeRegisterService {
    private final CargoRequestRepository cargoRequestRepository;
    private final StationCatalog stations;
    private final CalculationService calculationService;

    public VolumeRegisterService(
            CargoRequestRepository cargoRequestRepository,
            StationCatalog stations,
            CalculationService calculationService) {
        this.cargoRequestRepository = cargoRequestRepository;
        this.stations = stations;
        this.calculationService = calculationService;
    }

    @Transactional
    public Map<String, Object> registerItem(Map<String, Object> body) {
        String originCode = str(body.get("originTerminalCode"));
        String destCode = str(body.get("destinationTerminalCode"));
        if (originCode == null || destCode == null) {
            throw new IllegalArgumentException("출도착 터미널 코드가 필요합니다.");
        }
        StationCatalog.Station origin = stations.find(originCode)
                .orElseThrow(() -> new IllegalArgumentException("출발 터미널 없음: " + originCode));
        StationCatalog.Station dest = stations.find(destCode)
                .orElseThrow(() -> new IllegalArgumentException("도착 터미널 없음: " + destCode));

        int boxCount = intVal(body.get("boxCount"), 1);
        double volumeM3 = doubleVal(body.get("volumeM3"), 0.05);
        int fee = intVal(body.get("freightKrw"), 0);
        String product = str(body.get("productName"));
        if (product == null) product = "박스";
        String externalId = str(body.get("externalCargoId"));
        String photoUrl = str(body.get("photoUrl"));

        double fill = calculationService.calculateFillPercent(volumeM3, 50.0);

        CargoRequest req = new CargoRequest();
        req.setOrigin(origin.name());
        req.setDestination(dest.name());
        req.setOriginCode(origin.code());
        req.setDestinationCode(dest.code());
        req.setBoxCount(boxCount);
        req.setTotalVolumeM3(volumeM3);
        req.setProposedFee(fee);
        req.setExpectedFillPercent(fill);
        req.setStatus("PENDING");
        req.setBriefing((externalId != null ? externalId + " · " : "") + product
                + (photoUrl != null ? " · 사진등록" : ""));
        req.setNetProfit(fee);
        req = cargoRequestRepository.save(req);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "OK");
        out.put("requestId", req.getId());
        out.put("externalCargoId", externalId);
        out.put("originTerminalCode", origin.code());
        out.put("destinationTerminalCode", dest.code());
        out.put("boxCount", boxCount);
        out.put("volumeM3", volumeM3);
        out.put("fillPercentOf11t", fill);
        out.put("photoUrl", photoUrl);
        out.put("message", "기사 복화(OD) PENDING 반영 · #" + req.getId());
        return out;
    }

    private static String str(Object v) {
        if (v == null) return null;
        String s = String.valueOf(v).trim();
        return s.isEmpty() || "null".equals(s) ? null : s;
    }

    private static int intVal(Object v, int fallback) {
        if (v == null) return fallback;
        if (v instanceof Number n) return n.intValue();
        try { return Integer.parseInt(String.valueOf(v)); } catch (Exception e) { return fallback; }
    }

    private static double doubleVal(Object v, double fallback) {
        if (v == null) return fallback;
        if (v instanceof Number n) return n.doubleValue();
        try { return Double.parseDouble(String.valueOf(v)); } catch (Exception e) { return fallback; }
    }
}
