package com.moveai.backend.service;

import com.moveai.backend.entity.CargoOdGroup;
import com.moveai.backend.entity.CargoOdItem;
import com.moveai.backend.entity.CargoRequest;
import com.moveai.backend.repository.CargoOdGroupRepository;
import com.moveai.backend.repository.CargoOdItemRepository;
import com.moveai.backend.repository.CargoRequestRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;

/**
 * 시연용: 부산→서울 축 터미널에 OD 그룹 ~20개 배치 (그룹당 운송장 100~500).
 */
@Service
@RequiredArgsConstructor
public class DemoOdSeedService {

    private static final String ROUTE_PREFIX = "route:";
    private static final String DEMO_ITEM_PREFIX = "demo-";

    private final CargoOdGroupRepository groupRepository;
    private final CargoOdItemRepository itemRepository;
    private final CargoRequestRepository cargoRequestRepository;
    private final CalculationService calculationService;
    private final TerminalRegistryService terminalRegistry;
    private final TerminalDistanceMatrixService distanceMatrix;

    /** 경부 축 시연 터미널 (약 10곳) */
    private static final List<String> CORRIDOR = List.of(
            "200", // 부산강서
            "201", // 부산사상
            "300", // 대구북구
            "308", // 김천
            "500", // 대전대덕
            "501", // 대전유성
            "503", // 천안
            "514", // 진천
            "001", // 서울동부
            "008"  // 서울강남
    );

    /** origin → destination, 세 번째 = 박스(운송장) 수 100~500 */
    private static final List<String[]> ROUTES = List.of(
            // ===== 서울 방향 (부산·중간 → 서울) =====
            new String[]{"200", "001", "320"},
            new String[]{"200", "008", "280"},
            new String[]{"201", "001", "410"},
            new String[]{"201", "008", "190"},
            new String[]{"300", "001", "360"},
            new String[]{"300", "008", "240"},
            new String[]{"308", "001", "450"},
            new String[]{"308", "008", "220"},
            new String[]{"500", "001", "380"},
            new String[]{"500", "008", "260"},
            new String[]{"501", "001", "310"},
            new String[]{"501", "008", "170"},
            new String[]{"503", "001", "290"},
            new String[]{"503", "008", "155"},
            new String[]{"514", "001", "210"},
            new String[]{"514", "008", "130"},
            // ===== 부산 방향 (서울·중간 → 부산) =====
            new String[]{"001", "200", "350"},
            new String[]{"001", "201", "275"},
            new String[]{"008", "200", "300"},
            new String[]{"008", "201", "270"},
            new String[]{"514", "200", "180"},
            new String[]{"514", "201", "165"},
            new String[]{"503", "200", "220"},
            new String[]{"503", "201", "140"},
            new String[]{"501", "200", "195"},
            new String[]{"501", "201", "160"},
            new String[]{"500", "200", "200"},
            new String[]{"500", "201", "175"},
            new String[]{"308", "200", "250"},
            new String[]{"308", "201", "150"},
            new String[]{"300", "200", "180"},
            new String[]{"300", "201", "120"}
    );

    @Transactional
    public Map<String, Object> seedBusanSeoulCorridor(boolean clearExisting) {
        terminalRegistry.refresh(false);

        if (clearExisting) {
            itemRepository.deleteAll();
            groupRepository.deleteAll();
            for (CargoRequest req : cargoRequestRepository.findByStatusOrderByCreatedAtDesc("PENDING")) {
                String ext = req.getExternalCargoId();
                if (ext != null && ext.startsWith(ROUTE_PREFIX)) {
                    req.setStatus("UNMATCHED");
                    cargoRequestRepository.save(req);
                }
            }
        }

        LocalDateTime now = LocalDateTime.now();
        List<Map<String, Object>> preview = new ArrayList<>();
        int groups = 0;
        int items = 0;

        for (String[] row : ROUTES) {
            String oCode = row[0];
            String dCode = row[1];
            int waybills = Integer.parseInt(row[2]);
            var oTerm = terminalRegistry.findByCode(oCode).orElse(null);
            var dTerm = terminalRegistry.findByCode(dCode).orElse(null);
            if (oTerm == null || dTerm == null) {
                // 레지스트리에 없으면 하드코딩 좌표로 생성
                oTerm = oTerm != null ? oTerm : synthetic(oCode);
                dTerm = dTerm != null ? dTerm : synthetic(dCode);
            }
            if (oTerm == null || dTerm == null) continue;

            String routeKey = oCode + ":" + dCode;
            int boxes = waybills; // 1운송장 1박스 가정
            double vol = Math.round(waybills * 0.045 * 10000.0) / 10000.0;
            double weight = waybills * 8.0;
            int fee = waybills * 1500;
            double fill = calculationService.calculateFillPercentOf11t(vol);

            CargoOdGroup g = groupRepository.findByRouteKey(routeKey).orElseGet(CargoOdGroup::new);
            g.setRouteKey(routeKey);
            g.setOriginTerminalCode(oCode);
            g.setOriginTerminalName(oTerm.name());
            g.setDestinationTerminalCode(dCode);
            g.setDestinationTerminalName(dTerm.name());
            g.setOriginStationCode(oCode);
            g.setDestinationStationCode(dCode);
            g.setOriginLat(oTerm.lat());
            g.setOriginLng(oTerm.lng());
            g.setDestinationLat(dTerm.lat());
            g.setDestinationLng(dTerm.lng());
            g.setWaybillCount(waybills);
            g.setBoxCount(boxes);
            g.setVolumeM3(vol);
            g.setWeightKg(weight);
            g.setFreightKrw(fee);
            g.setFillPercentOf11t(fill);
            g.setFillByVehicleJson(calculationService.toFillByVehicleJson(vol));
            g.setUpdatedAt(now);
            g = groupRepository.save(g);

            // 목록용 샘플 아이템 (최대 40) — 집계 waybillCount는 100~500 유지
            int sampleN = Math.min(40, waybills);
            for (int i = 0; i < sampleN; i++) {
                String ext = DEMO_ITEM_PREFIX + routeKey.replace(':', '-') + "-" + (i + 1);
                if (itemRepository.findByExternalCargoId(ext).isPresent()) continue;
                itemRepository.save(CargoOdItem.builder()
                        .odGroupId(g.getId())
                        .externalCargoId(ext)
                        .originTerminalCode(oCode)
                        .destinationTerminalCode(dCode)
                        .boxCount(1)
                        .volumeM3(0.045)
                        .weightKg(8.0)
                        .freightKrw(1500)
                        .productCode("Box")
                        .productName("시연박스")
                        .status("WAITING")
                        .createdAt(now)
                        .build());
                items++;
            }

            Long reqId = upsertRequest(g);
            g.setCargoRequestId(reqId);
            groupRepository.save(g);
            groups++;

            Map<String, Object> p = new LinkedHashMap<>();
            p.put("routeKey", routeKey);
            p.put("origin", oTerm.name());
            p.put("destination", dTerm.name());
            p.put("waybills", waybills);
            p.put("fillPercent", fill);
            p.put("cargoRequestId", reqId);
            preview.add(p);
        }

        // N×N 전체 warm은 카카오 폭주로 타임아웃 → 시드 응답 후 필요 쌍만 비동기
        final List<String[]> routePairs = new ArrayList<>(ROUTES);
        Thread t = new Thread(() -> {
            try {
                Set<String> codes = new LinkedHashSet<>(CORRIDOR);
                // 직행 O→D + 각 그룹 pick→drop 만
                List<String> pairFlat = new ArrayList<>();
                for (String[] row : routePairs) {
                    pairFlat.add(row[0] + ">" + row[1]);
                    distanceMatrix.leg(row[0], row[1]);
                }
                // 서울↔부산 직행
                distanceMatrix.leg("200", "001");
                distanceMatrix.leg("200", "008");
                distanceMatrix.leg("001", "200");
                // corridor 인접 구간만 (전체 N×N 금지)
                for (int i = 0; i < CORRIDOR.size() - 1; i++) {
                    distanceMatrix.leg(CORRIDOR.get(i), CORRIDOR.get(i + 1));
                    distanceMatrix.leg(CORRIDOR.get(i + 1), CORRIDOR.get(i));
                }
            } catch (Exception ignored) {}
        }, "warm-demo-distance");
        t.setDaemon(true);
        t.start();

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("mode", "demo-busan-seoul");
        out.put("terminals", CORRIDOR);
        out.put("groupsCreated", groups);
        out.put("sampleItems", items);
        out.put("tableCount", groupRepository.count());
        out.put("distanceMatrix", Map.of("status", "warming-async", "note", "route pairs only"));
        out.put("preview", preview);
        out.put("message", "서울·부산 양방향 시연 그룹 " + groups + "개 배치 (터미널 " + CORRIDOR.size()
                + ", 그룹당 100~500박스)");
        return out;
    }

    private Long upsertRequest(CargoOdGroup g) {
        String ext = ROUTE_PREFIX + g.getRouteKey();
        CargoRequest req = cargoRequestRepository.findByExternalCargoId(ext).orElseGet(CargoRequest::new);
        req.setExternalCargoId(ext);
        req.setOrigin(g.getOriginTerminalName());
        req.setDestination(g.getDestinationTerminalName());
        req.setViaStation("운송장 " + g.getWaybillCount() + "건");
        req.setOriginCode(g.getOriginTerminalCode());
        req.setDestinationCode(g.getDestinationTerminalCode());
        req.setBoxCount(g.getBoxCount());
        req.setTotalVolumeM3(g.getVolumeM3());
        req.setTotalWeightKg(g.getWeightKg());
        req.setProposedFee(g.getFreightKrw());
        req.setExpectedFillPercent(g.getFillPercentOf11t());
        req.setStatus("PENDING");
        if (req.getCreatedAt() == null) req.setCreatedAt(LocalDateTime.now());
        return cargoRequestRepository.save(req).getId();
    }

    private TerminalRegistryService.Terminal synthetic(String code) {
        return switch (code) {
            case "200" -> new TerminalRegistryService.Terminal("200", "부산강서터미널", "부산", 35.1362, 128.8300);
            case "201" -> new TerminalRegistryService.Terminal("201", "부산사상터미널", "부산", 35.1526, 128.9910);
            case "300" -> new TerminalRegistryService.Terminal("300", "대구북구터미널", "대구", 35.8858, 128.5828);
            case "308" -> new TerminalRegistryService.Terminal("308", "김천터미널", "김천", 36.1398, 128.1136);
            case "500" -> new TerminalRegistryService.Terminal("500", "대전대덕터미널", "대전", 36.4194, 127.4310);
            case "501" -> new TerminalRegistryService.Terminal("501", "대전유성터미널", "대전", 36.4102, 127.3894);
            case "503" -> new TerminalRegistryService.Terminal("503", "천안터미널", "천안", 36.8151, 127.1139);
            case "514" -> new TerminalRegistryService.Terminal("514", "진천터미널", "진천", 36.8555, 127.4356);
            case "001" -> new TerminalRegistryService.Terminal("001", "서울동부터미널", "서울", 37.5745, 127.0555);
            case "008" -> new TerminalRegistryService.Terminal("008", "서울강남터미널", "서울", 37.5172, 127.0473);
            default -> null;
        };
    }
}
