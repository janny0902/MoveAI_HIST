package com.moveai.backend.service;

import com.moveai.backend.entity.CargoOdGroup;
import com.moveai.backend.entity.CargoOdItem;
import com.moveai.backend.entity.CargoRequest;
import com.moveai.backend.repository.CargoOdGroupRepository;
import com.moveai.backend.repository.CargoOdItemRepository;
import com.moveai.backend.repository.CargoRequestRepository;
import com.moveai.backend.station.KtxStations;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;

/**
 * 단건 등록 → OD 그룹 자동 합산, 그룹 상세, 수락 후 다음 OD로 이동(시연).
 */
@Service
@RequiredArgsConstructor
public class CargoOdGroupService {

    private static final String ROUTE_PREFIX = "route:";

    private final CargoOdGroupRepository groupRepository;
    private final CargoOdItemRepository itemRepository;
    private final CargoRequestRepository cargoRequestRepository;
    private final CalculationService calculationService;
    private final TerminalRegistryService terminalRegistry;

    public record RegisterItemRequest(
            String externalCargoId,
            String originTerminalCode,
            String destinationTerminalCode,
            String originTerminalName,
            String destinationTerminalName,
            Integer boxCount,
            Double volumeM3,
            Double weightKg,
            Integer freightKrw,
            String productCode,
            String productName,
            String originStationCode,
            String destinationStationCode,
            String photoUrl
    ) {}

    @Transactional
    public Map<String, Object> registerItem(RegisterItemRequest body) {
        String oTerm = nz(body.originTerminalCode(), "200");
        String dTerm = nz(body.destinationTerminalCode(), "001");
        TerminalRegistryService.Terminal oT = terminalRegistry.findByCode(oTerm).orElse(null);
        TerminalRegistryService.Terminal dT = terminalRegistry.findByCode(dTerm).orElse(null);
        String oName = nz(body.originTerminalName(), oT != null ? oT.name() : oTerm);
        String dName = nz(body.destinationTerminalName(), dT != null ? dT.name() : dTerm);
        Double oLat = oT != null ? oT.lat() : null;
        Double oLng = oT != null ? oT.lng() : null;
        Double dLat = dT != null ? dT.lat() : null;
        Double dLng = dT != null ? dT.lng() : null;

        String routeKey = oTerm + ":" + dTerm;
        CargoOdGroup group = groupRepository.findByRouteKey(routeKey).orElseGet(() -> {
            CargoOdGroup g = new CargoOdGroup();
            g.setRouteKey(routeKey);
            g.setOriginTerminalCode(oTerm);
            g.setDestinationTerminalCode(dTerm);
            g.setOriginTerminalName(oName);
            g.setDestinationTerminalName(dName);
            g.setOriginStationCode(oTerm);
            g.setDestinationStationCode(dTerm);
            g.setOriginLat(oLat);
            g.setOriginLng(oLng);
            g.setDestinationLat(dLat);
            g.setDestinationLng(dLng);
            g.setWaybillCount(0);
            g.setBoxCount(0);
            g.setVolumeM3(0.0);
            g.setWeightKg(0.0);
            g.setFreightKrw(0);
            g.setFillPercentOf11t(0.0);
            g.setFillByVehicleJson("{}");
            g.setUpdatedAt(LocalDateTime.now());
            return groupRepository.save(g);
        });
        if (group.getOriginLat() == null && oLat != null) {
            group.setOriginLat(oLat);
            group.setOriginLng(oLng);
            group.setDestinationLat(dLat);
            group.setDestinationLng(dLng);
            groupRepository.save(group);
        }

        String extId = body.externalCargoId();
        if (extId == null || extId.isBlank()) {
            extId = "local-" + UUID.randomUUID().toString().substring(0, 8);
        }
        Optional<CargoOdItem> existing = itemRepository.findByExternalCargoId(extId);
        if (existing.isPresent()) {
            return Map.of(
                    "duplicated", true,
                    "itemId", existing.get().getId(),
                    "odGroupId", existing.get().getOdGroupId(),
                    "message", "이미 등록된 운송장입니다."
            );
        }

        String productCode = nz(body.productCode(), "Box");
        String productName = nz(body.productName(), productLabel(productCode));
        int boxes = body.boxCount() != null && body.boxCount() > 0 ? body.boxCount() : 1;
        double vol = body.volumeM3() != null ? body.volumeM3() : 0.05;
        double weight = body.weightKg() != null ? body.weightKg() : boxes * 8.0;

        // 박스만 자동 요금(프론트 미전달 시 기본 A형×수량). 비박스는 화주 운임 필수(0원 이상 허용).
        boolean isBox = "Box".equalsIgnoreCase(productCode);
        Integer feeIn = body.freightKrw();
        if (!isBox && feeIn == null) {
            throw new IllegalArgumentException("행낭·파렛트 등 비박스 화물은 화주 운임(원)을 0 이상으로 입력해야 합니다.");
        }
        if (feeIn != null && feeIn < 0) {
            throw new IllegalArgumentException("화주 운임은 0원 이상이어야 합니다.");
        }
        int fee = feeIn != null ? feeIn : boxes * 6000;

        CargoOdItem item = itemRepository.save(CargoOdItem.builder()
                .odGroupId(group.getId())
                .externalCargoId(extId)
                .originTerminalCode(oTerm)
                .destinationTerminalCode(dTerm)
                .boxCount(boxes)
                .volumeM3(vol)
                .weightKg(weight)
                .freightKrw(fee)
                .productCode(productCode)
                .productName(productName)
                .photoUrl(blankToNull(body.photoUrl()))
                .status("WAITING")
                .createdAt(LocalDateTime.now())
                .build());

        refreshGroupTotals(group);
        Long reqId = ensurePendingRequest(group, true);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("registered", true);
        out.put("itemId", item.getId());
        out.put("externalCargoId", extId);
        out.put("odGroupId", group.getId());
        out.put("routeKey", group.getRouteKey());
        out.put("originTerminalCode", group.getOriginTerminalCode());
        out.put("destinationTerminalCode", group.getDestinationTerminalCode());
        out.put("waybillCount", group.getWaybillCount());
        out.put("boxCount", group.getBoxCount());
        out.put("volumeM3", group.getVolumeM3());
        out.put("freightKrw", group.getFreightKrw());
        out.put("productSummary", group.getProductSummary());
        out.put("photoUrl", group.getPhotoUrl());
        out.put("fillPercentOf11t", group.getFillPercentOf11t());
        out.put("fillByVehicle", calculationService.parseFillByVehicleJson(group.getFillByVehicleJson()));
        out.put("cargoRequestId", reqId);
        out.put("message", group.getOriginTerminalName() + " → " + group.getDestinationTerminalName()
                + " 그룹에 합류 (운송장 " + group.getWaybillCount() + "건)");
        return out;
    }

    public List<CargoOdItem> listItems(Long odGroupId) {
        return itemRepository.findByOdGroupIdOrderByIdAsc(odGroupId);
    }

    public Optional<CargoOdGroup> findGroup(Long id) {
        return groupRepository.findById(id);
    }

    public Optional<CargoOdGroup> findByCargoRequestId(Long requestId) {
        return groupRepository.findByCargoRequestId(requestId);
    }

    @Transactional
    public void refreshGroupTotals(CargoOdGroup group) {
        List<CargoOdItem> items = itemRepository.findByOdGroupIdOrderByIdAsc(group.getId());
        int waybills = 0;
        int boxes = 0;
        double vol = 0;
        double weight = 0;
        int fee = 0;
        String latestPhoto = null;
        Map<String, Integer> productQty = new LinkedHashMap<>();
        for (CargoOdItem it : items) {
            if ("DONE".equals(it.getStatus())) continue;
            waybills++;
            int qty = it.getBoxCount() != null ? it.getBoxCount() : 1;
            boxes += qty;
            vol += it.getVolumeM3() != null ? it.getVolumeM3() : 0;
            weight += it.getWeightKg() != null ? it.getWeightKg() : 0;
            fee += it.getFreightKrw() != null ? it.getFreightKrw() : 0;
            String label = it.getProductName() != null && !it.getProductName().isBlank()
                    ? it.getProductName().replace("(그룹사진)", "").trim()
                    : productLabel(it.getProductCode());
            // 그룹사진 접미사 제거 후 집계
            if (label.endsWith("(그룹사진)")) label = label.replace("(그룹사진)", "").trim();
            productQty.merge(label, qty, Integer::sum);
            if (it.getPhotoUrl() != null && !it.getPhotoUrl().isBlank()) {
                latestPhoto = it.getPhotoUrl();
            }
        }
        group.setWaybillCount(waybills);
        group.setBoxCount(boxes);
        group.setVolumeM3(Math.round(vol * 10000.0) / 10000.0);
        group.setWeightKg(weight);
        group.setFreightKrw(fee);
        group.setFillPercentOf11t(calculationService.calculateFillPercentOf11t(vol));
        group.setFillByVehicleJson(calculationService.toFillByVehicleJson(vol));
        group.setProductSummary(formatProductSummary(productQty));
        if (latestPhoto != null) group.setPhotoUrl(latestPhoto);
        group.setUpdatedAt(LocalDateTime.now());
        groupRepository.save(group);
        ensurePendingRequest(group, false);
    }

    private static String formatProductSummary(Map<String, Integer> productQty) {
        if (productQty == null || productQty.isEmpty()) return null;
        List<String> parts = new ArrayList<>();
        for (Map.Entry<String, Integer> e : productQty.entrySet()) {
            parts.add(e.getKey() + " " + e.getValue());
        }
        return String.join(" · ", parts);
    }

    private static String productLabel(String code) {
        if (code == null) return "박스";
        return switch (code.trim()) {
            case "Box" -> "박스";
            case "Bag", "Pouch" -> "행낭";
            case "Pallet" -> "파렛트";
            case "Poly" -> "폴리백";
            case "Sack" -> "포대";
            case "Vinyl" -> "기타";
            default -> code;
        };
    }

    private static String blankToNull(String v) {
        if (v == null || v.isBlank()) return null;
        return v.trim();
    }

    private static String nz(String v, String d) {
        return v != null && !v.isBlank() ? v.trim() : d;
    }

    /**
     * 시연: 수락·출발 후 그룹을 다음 출도착(경부축)으로 옮긴다.
     * A→B 수락 → B→C(기사 목적지 방향) 로 route_key 변경, 아이템 OD 갱신, 다시 PENDING.
     */
    @Transactional
    public Map<String, Object> advanceAfterAccept(Long cargoRequestId, String driverDestCode) {
        CargoOdGroup group = findByCargoRequestId(cargoRequestId).orElse(null);
        if (group == null) {
            return Map.of("advanced", false, "reason", "no-od-group");
        }

        // 터미널 코드일 수 있으므로 GPS → 경부축 KTX로 투영
        KtxStations.Station from = KtxStations.findByCode(group.getDestinationStationCode()).orElse(null);
        if (from == null && group.getDestinationLat() != null && group.getDestinationLng() != null) {
            from = KtxStations.nearest(group.getDestinationLat(), group.getDestinationLng());
        }
        if (from == null) {
            from = terminalRegistry.findByCode(group.getDestinationTerminalCode())
                    .map(t -> KtxStations.nearest(t.lat(), t.lng()))
                    .orElse(KtxStations.findByCode("BUSAN").orElseThrow());
        }
        String driverKtx = driverDestCode;
        if (terminalRegistry.findByCode(driverDestCode).isPresent()) {
            var dt = terminalRegistry.findByCode(driverDestCode).get();
            driverKtx = KtxStations.nearest(dt.lat(), dt.lng()).code();
        }
        KtxStations.Station next = KtxStations.nextToward(from.code(), driverKtx)
                .orElse(KtxStations.findByCode("SEOUL").orElseThrow());

        if (from.code().equalsIgnoreCase(next.code())) {
            // 최종 목적지 도착 — 아이템 DONE, 그룹 비활성
            for (CargoOdItem it : itemRepository.findByOdGroupIdOrderByIdAsc(group.getId())) {
                it.setStatus("DONE");
                itemRepository.save(it);
            }
            refreshGroupTotals(group);
            return Map.of(
                    "advanced", false,
                    "reason", "arrived",
                    "message", "최종 구간 도착 — 그룹 종료",
                    "station", from.name()
            );
        }

        // 다음 구간도 작업터미널로: 각 KTX 근처 터미널 선택
        String newTermO = nearestTerminalCode(from.lat(), from.lng(), from.code());
        String newTermD = nearestTerminalCode(next.lat(), next.lng(), next.code());
        String newRouteKey = newTermO + ":" + newTermD;
        String oldKey = group.getRouteKey();
        var oTerm = terminalRegistry.findByCode(newTermO);
        var dTerm = terminalRegistry.findByCode(newTermD);
        String oName = oTerm.map(TerminalRegistryService.Terminal::name).orElse(from.name());
        String dName = dTerm.map(TerminalRegistryService.Terminal::name).orElse(next.name());
        Double oLat = oTerm.map(TerminalRegistryService.Terminal::lat).orElse(from.lat());
        Double oLng = oTerm.map(TerminalRegistryService.Terminal::lng).orElse(from.lng());
        Double dLat = dTerm.map(TerminalRegistryService.Terminal::lat).orElse(next.lat());
        Double dLng = dTerm.map(TerminalRegistryService.Terminal::lng).orElse(next.lng());

        // 기존 route_key 유니크 충돌 방지: 임시 키 후 이동
        Optional<CargoOdGroup> clash = groupRepository.findByRouteKey(newRouteKey);
        if (clash.isPresent() && !clash.get().getId().equals(group.getId())) {
            // 다음 OD 그룹이 이미 있으면 아이템을 그쪽으로 합류
            CargoOdGroup target = clash.get();
            for (CargoOdItem it : itemRepository.findByOdGroupIdOrderByIdAsc(group.getId())) {
                if ("DONE".equals(it.getStatus())) continue;
                it.setOdGroupId(target.getId());
                it.setOriginTerminalCode(newTermO);
                it.setDestinationTerminalCode(newTermD);
                it.setStatus("WAITING");
                itemRepository.save(it);
            }
            refreshGroupTotals(group);
            refreshGroupTotals(target);
            Long reqId = ensurePendingRequest(target, true);
            return Map.of(
                    "advanced", true,
                    "mergedInto", target.getId(),
                    "fromRoute", oldKey,
                    "toRoute", newRouteKey,
                    "cargoRequestId", reqId,
                    "message", target.getOriginTerminalName() + " → " + target.getDestinationTerminalName() + " 로 합류"
            );
        }

        group.setRouteKey(newRouteKey);
        group.setOriginTerminalCode(newTermO);
        group.setDestinationTerminalCode(newTermD);
        group.setOriginTerminalName(oName);
        group.setDestinationTerminalName(dName);
        group.setOriginStationCode(newTermO);
        group.setDestinationStationCode(newTermD);
        group.setOriginLat(oLat);
        group.setOriginLng(oLng);
        group.setDestinationLat(dLat);
        group.setDestinationLng(dLng);
        groupRepository.save(group);

        for (CargoOdItem it : itemRepository.findByOdGroupIdOrderByIdAsc(group.getId())) {
            if ("DONE".equals(it.getStatus())) continue;
            it.setOriginTerminalCode(newTermO);
            it.setDestinationTerminalCode(newTermD);
            it.setStatus("WAITING");
            itemRepository.save(it);
        }
        refreshGroupTotals(group);

        // 수락으로 ASSIGNED 된 request를 새 OD PENDING으로 재오픈
        Long reqId = group.getCargoRequestId();
        if (reqId != null) {
            cargoRequestRepository.findById(reqId).ifPresent(req -> {
                req.setStatus("PENDING");
                req.setAssignedTruckId(null);
                req.setAssignedDriverName(null);
                req.setOrigin(group.getOriginTerminalName());
                req.setDestination(group.getDestinationTerminalName());
                req.setOriginCode(group.getOriginTerminalCode());
                req.setDestinationCode(group.getDestinationTerminalCode());
                req.setViaStation("운송장 " + group.getWaybillCount() + "건 · 다음구간");
                req.setBoxCount(group.getBoxCount());
                req.setTotalVolumeM3(group.getVolumeM3());
                req.setTotalWeightKg(group.getWeightKg());
                req.setProposedFee(group.getFreightKrw());
                req.setExpectedFillPercent(group.getFillPercentOf11t());
                req.setExternalCargoId(ROUTE_PREFIX + group.getRouteKey());
                cargoRequestRepository.save(req);
            });
        } else {
            reqId = ensurePendingRequest(group, false);
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("advanced", true);
        out.put("fromRoute", oldKey);
        out.put("toRoute", newRouteKey);
        out.put("odGroupId", group.getId());
        out.put("cargoRequestId", reqId);
        out.put("message", oName + " → " + dName + " 다음 구간으로 이동 (시연)");
        return out;
    }

    private String nearestTerminalCode(double lat, double lng, String fallback) {
        TerminalRegistryService.Terminal best = null;
        double bestD = Double.MAX_VALUE;
        for (TerminalRegistryService.Terminal t : terminalRegistry.listTerminals()) {
            double d = KtxStations.haversine(lat, lng, t.lat(), t.lng());
            if (d < bestD) {
                bestD = d;
                best = t;
            }
        }
        return best != null ? best.code() : fallback;
    }

    /**
     * @param reopenIfAssigned true면 이미 수락된 OD에 새 물량 등록 시 PENDING으로 재오픈
     */
    private Long ensurePendingRequest(CargoOdGroup g, boolean reopenIfAssigned) {
        String ext = ROUTE_PREFIX + g.getRouteKey();
        CargoRequest req = cargoRequestRepository.findByExternalCargoId(ext).orElseGet(CargoRequest::new);
        if (req.getId() != null
                && !"PENDING".equals(req.getStatus())
                && !"UNMATCHED".equals(req.getStatus())
                && !"ASSIGNED".equals(req.getStatus())
                && !"COMPLETED".equals(req.getStatus())) {
            return req.getId();
        }
        if (req.getId() != null && "ASSIGNED".equals(req.getStatus()) && !reopenIfAssigned) {
            g.setCargoRequestId(req.getId());
            groupRepository.save(g);
            return req.getId();
        }
        // 신규·UNMATCHED·COMPLETED, 또는 수락 후 재등록 → PENDING으로 복화 목록/핀에 노출
        req.setExternalCargoId(ext);
        req.setOrigin(g.getOriginTerminalName());
        req.setDestination(g.getDestinationTerminalName());
        req.setViaStation("운송장 " + (g.getWaybillCount() != null ? g.getWaybillCount() : 0) + "건");
        req.setOriginCode(g.getOriginTerminalCode());
        req.setDestinationCode(g.getDestinationTerminalCode());
        req.setBoxCount(g.getBoxCount());
        req.setTotalVolumeM3(g.getVolumeM3());
        req.setTotalWeightKg(g.getWeightKg());
        req.setProposedFee(g.getFreightKrw());
        req.setExpectedFillPercent(g.getFillPercentOf11t());
        req.setStatus("PENDING");
        req.setAssignedTruckId(null);
        req.setAssignedDriverName(null);
        if (req.getCreatedAt() == null) req.setCreatedAt(LocalDateTime.now());
        req = cargoRequestRepository.save(req);
        g.setCargoRequestId(req.getId());
        groupRepository.save(g);
        return req.getId();
    }
}
