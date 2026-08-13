package com.moveai.backend.controller;

import com.moveai.backend.entity.CargoRequest;
import com.moveai.backend.entity.LoadHistory;
import com.moveai.backend.entity.Truck;
import com.moveai.backend.entity.VolumetricCargo;
import com.moveai.backend.entity.VolumetricGroup;
import com.moveai.backend.entity.VolumetricGroupItem;
import com.moveai.backend.repository.CargoRequestRepository;
import com.moveai.backend.repository.LoadHistoryRepository;
import com.moveai.backend.repository.TruckRepository;
import com.moveai.backend.repository.VolumetricCargoRepository;
import com.moveai.backend.repository.VolumetricGroupItemRepository;
import com.moveai.backend.repository.VolumetricGroupRepository;
import com.moveai.backend.entity.CargoOdItem;
import com.moveai.backend.service.AdminCargoBridgeService;
import com.moveai.backend.service.CalculationService;
import com.moveai.backend.service.CargoOdGroupService;
import com.moveai.backend.service.DemoOdSeedService;
import com.moveai.backend.service.DispatchCartService;
import com.moveai.backend.service.KakaoNaviService;
import com.moveai.backend.service.OdDetourService;
import com.moveai.backend.service.OptimalDispatchService;
import com.moveai.backend.service.RouteMatchService;
import com.moveai.backend.service.TerminalDistanceMatrixService;
import com.moveai.backend.service.TerminalRegistryService;
import com.moveai.backend.station.KtxStations;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;

import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/dispatch")
@RequiredArgsConstructor
public class DispatchController {

    private final CalculationService calculationService;
    private final CargoRequestRepository cargoRequestRepository;
    private final TruckRepository truckRepository;
    private final LoadHistoryRepository loadHistoryRepository;
    private final VolumetricCargoRepository volumetricCargoRepository;
    private final VolumetricGroupRepository volumetricGroupRepository;
    private final VolumetricGroupItemRepository volumetricGroupItemRepository;
    private final KakaoNaviService kakaoNaviService;
    private final RouteMatchService routeMatchService;
    private final AdminCargoBridgeService adminCargoBridgeService;
    private final CargoOdGroupService cargoOdGroupService;
    private final TerminalRegistryService terminalRegistry;
    private final OdDetourService odDetourService;
    private final OptimalDispatchService optimalDispatchService;
    private final DemoOdSeedService demoOdSeedService;
    private final TerminalDistanceMatrixService terminalDistanceMatrixService;
    private final DispatchCartService dispatchCartService;
    private final RestTemplate restTemplate;

    /** 시연 리셋마다 증가. 기사 앱이 운행 세션을 같이 비울 때 쓴다. */
    private static final AtomicLong DEMO_EPOCH = new AtomicLong(0);

    @Data
    public static class CargoItemDto {
        private String cargo_id;
        private String type;
        private double width;
        private double length;
        private double height;
        private double volume_cm3;
    }

    @Data
    public static class AcceptRequestDto {
        private Long truckId;
        /** 일괄 수락 시 다음 OD 자동 이동 생략 */
        private Boolean skipOdAdvance;
        /** 기사 화면 계획 잔여(%). 있으면 트럭 DB 잔여 대신 사용 */
        private Double remainingPercent;
        /** 이번 수락 물량 fill% */
        private Double fillPercent;
    }

    @Data
    public static class BatchAcceptDto {
        private Long truckId;
        private List<Long> requestIds;
    }

    @Data
    public static class CartPreviewDto {
        private Long truckId;
        private List<Long> odGroupIds;
    }

    @Data
    public static class ProposeRequestDto {
        private String origin;
        private String destination;
        private String via;
        private String originCode;
        private String destinationCode;
        private String viaCode;
        /** 경유 역 코드 (최대 4개) */
        private List<String> viaCodes;
        private Long groupId;
        private List<CargoItemDto> selectedCargo;
        private int fee;
    }

    @GetMapping("/stations")
    public Map<String, Object> stations() {
        // 하위호환: 작업터미널을 stations 형태로도 반환
        return terminals();
    }

    /** 관리자·기사 공통 작업터미널 목록 */
    @GetMapping("/terminals")
    public Map<String, Object> terminals() {
        List<Map<String, Object>> list = terminalRegistry.listTerminals().stream()
                .map(TerminalRegistryService.Terminal::toMap)
                .collect(Collectors.toList());
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("terminals", list);
        out.put("stations", list); // 프론트 기존 stations 키 호환
        out.put("count", list.size());
        return out;
    }

    /** 카카오 로컬로 터미널 GPS 보정 (시연 1회) */
    @PostMapping("/terminals/refresh-gps")
    public Map<String, Object> refreshTerminalGps(
            @RequestParam(defaultValue = "true") boolean refreshGps
    ) {
        return terminalRegistry.refresh(refreshGps);
    }

    /**
     * 11톤 기준 적재율 그룹 목록 (5/10/30/50/90%)
     */
    @GetMapping("/cargo-groups")
    public Map<String, Object> getCargoGroups() {
        List<VolumetricGroup> groups = volumetricGroupRepository.findAllByOrderByFillPercentAsc();
        List<Map<String, Object>> list = groups.stream().map(g -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", g.getId());
            m.put("group_code", g.getGroupCode());
            m.put("fill_percent", g.getFillPercent());
            m.put("target_volume_m3", g.getTargetVolumeM3());
            m.put("actual_volume_m3", g.getActualVolumeM3());
            m.put("actual_fill_percent", g.getActualFillPercent());
            m.put("box_count", g.getBoxCount());
            m.put("truck_capacity_m3", g.getTruckCapacityM3());
            return m;
        }).collect(Collectors.toList());

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("groups", list);
        response.put("truck_capacity_m3", CalculationService.TRUCK_CAPACITY_M3_11T);
        response.put("truck_spec", "11톤 윙바디 2.35×9.30×2.45m · 30.545m³ · 11000kg");
        return response;
    }

    /**
     * 선택한 그룹의 물품 목록
     */
    @GetMapping("/cargo-groups/{id}/items")
    public Map<String, Object> getCargoGroupItems(@PathVariable Long id) {
        VolumetricGroup group = volumetricGroupRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("그룹 없음: " + id));
        List<VolumetricGroupItem> items = volumetricGroupItemRepository.findByGroupIdOrderByIdAsc(id);

        List<Map<String, Object>> pool = items.stream().map(v -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("cargo_id", v.getCargoId());
            item.put("type", v.getCargoType());
            item.put("width", v.getWidthMm());
            item.put("length", v.getLengthMm());
            item.put("height", v.getHeightMm());
            item.put("dim_unit", "mm");
            item.put("volume_cm3", v.getVolumeCm3());
            item.put("volume_m3", v.getVolumeM3());
            return item;
        }).collect(Collectors.toList());

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("group", Map.of(
                "id", group.getId(),
                "group_code", group.getGroupCode(),
                "fill_percent", group.getFillPercent(),
                "actual_volume_m3", group.getActualVolumeM3(),
                "actual_fill_percent", group.getActualFillPercent(),
                "box_count", group.getBoxCount()
        ));
        response.put("cargo_pool", pool);
        return response;
    }

    /**
     * DB에 이관된 체적(물품) 데이터에서 풀 조회
     */
    @GetMapping("/cargo-pool")
    public Map<String, Object> getCargoPool(
            @RequestParam(defaultValue = "500") int limit,
            @RequestParam(required = false) String source
    ) {
        int safeLimit = Math.max(1, Math.min(limit, 2000));
        String sourceFilter = (source == null || source.isBlank()) ? null : source.trim();

        long total = sourceFilter == null
                ? volumetricCargoRepository.count()
                : volumetricCargoRepository.countBySourceFile(sourceFilter);

        List<VolumetricCargo> rows = volumetricCargoRepository.findPool(
                sourceFilter, PageRequest.of(0, safeLimit));

        List<Map<String, Object>> pool = rows.stream().map(v -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("cargo_id", v.getCargoId());
            item.put("type", v.getCargoType());
            item.put("width", v.getWidthMm());
            item.put("length", v.getLengthMm());
            item.put("height", v.getHeightMm());
            item.put("dim_unit", "mm");
            item.put("volume_cm3", v.getVolumeCm3());
            item.put("volume_m3", v.getVolumeM3());
            item.put("source_file", v.getSourceFile());
            return item;
        }).collect(Collectors.toList());

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("cargo_pool", pool);
        response.put("total_count", total);
        response.put("returned_count", pool.size());
        response.put("truck_capacity_m3", CalculationService.TRUCK_CAPACITY_M3_11T);
        response.put("truck_spec", "11톤 윙바디 2.35×9.30×2.45m · 30.545m³ · 11000kg");
        response.put("source", "postgresql:volumetric_cargo");
        return response;
    }

    /**
     * 2. 시연자가 직접 고른 박스 데이터를 기반으로 정밀 매칭 및 복화 제안 생성
     */
    @PostMapping("/propose")
    public Map<String, Object> proposeDispatch(@RequestBody ProposeRequestDto body) {
        List<String> logs = new ArrayList<>();

        List<CargoItemDto> selected = body.getSelectedCargo();
        Long selectedGroupId = body.getGroupId();
        if ((selected == null || selected.isEmpty()) && selectedGroupId != null) {
            VolumetricGroup group = volumetricGroupRepository.findById(selectedGroupId)
                    .orElseThrow(() -> new IllegalArgumentException("그룹 없음: " + selectedGroupId));
            List<VolumetricGroupItem> items = volumetricGroupItemRepository.findByGroupIdOrderByIdAsc(selectedGroupId);
            selected = items.stream().map(v -> {
                CargoItemDto dto = new CargoItemDto();
                dto.setCargo_id(v.getCargoId());
                dto.setType(v.getCargoType());
                dto.setWidth(v.getWidthMm() != null ? v.getWidthMm() : 0);
                dto.setLength(v.getLengthMm() != null ? v.getLengthMm() : 0);
                dto.setHeight(v.getHeightMm() != null ? v.getHeightMm() : 0);
                dto.setVolume_cm3(v.getVolumeCm3());
                return dto;
            }).collect(Collectors.toList());
            logs.add("[1] 체적 그룹 선택: " + group.getGroupCode()
                    + " (목표 " + group.getFillPercent() + "% / 실제 "
                    + group.getActualFillPercent() + "% / " + group.getBoxCount() + "박스)");
        } else {
            if (selected == null) selected = Collections.emptyList();
            logs.add("[1] 선택한 체적 데이터 수신 시작 (수량: " + selected.size() + "개)");
        }

        if (selected.isEmpty()) {
            return Map.of("matched", false, "logs", logs, "message", "선택된 체적 그룹/물품이 없습니다.");
        }

        String origin = body.getOrigin() != null ? body.getOrigin() : "부산터미널(부산역)";
        String destination = body.getDestination() != null ? body.getDestination() : "서울터미널(서울역)";

        // 선택된 박스의 정확한 부피 합계 계산 (cm3 -> m3)
        double totalVolumeCm3 = selected.stream()
                .mapToDouble(CargoItemDto::getVolume_cm3)
                .sum();
        double totalVolumeM3 = totalVolumeCm3 / 1_000_000.0;
        totalVolumeM3 = Math.round(totalVolumeM3 * 10000.0) / 10000.0;

        // 가상 무게 계산 (박스 수 * 평균 8kg)
        double totalWeightKg = selected.size() * 8.5;
        double fillPercentOf11t = calculationService.calculateFillPercentOf11t(totalVolumeM3);
        if (selectedGroupId != null) {
            VolumetricGroup g = volumetricGroupRepository.findById(selectedGroupId).orElse(null);
            if (g != null && g.getActualFillPercent() != null) {
                fillPercentOf11t = g.getActualFillPercent();
            }
        }

        logs.add("[2] 계산된 적재 필요 부피: " + totalVolumeM3 + " m³ / 예상 총 무게: " + totalWeightKg + " kg");
        logs.add("[2-1] 11톤 기준(" + CalculationService.TRUCK_CAPACITY_M3_11T + "m³) 점유율: " + fillPercentOf11t + "%");

        // 배차: 잔여공간 되는 등록 기사 전원에게 알림 (경로 무관 — 리스트는 경로 필터)
        List<Truck> trucks = truckRepository.findAll().stream()
                .filter(t -> Boolean.TRUE.equals(t.getProfileCompleted()))
                .toList();
        logs.add("[3] 등록 기사 검색... (" + trucks.size() + "대)");

        final double needFill = fillPercentOf11t;
        List<Truck> eligible = trucks.stream()
                .filter(t -> {
                    double rem = t.getRemainingVolumePercent() != null ? t.getRemainingVolumePercent() : 100.0;
                    return rem + 0.01 >= needFill;
                })
                .toList();

        KtxStations.Station originSt = resolveStation(body.getOriginCode(), origin, "BUSAN");
        KtxStations.Station destSt = resolveStation(body.getDestinationCode(), destination, "SEOUL");
        List<KtxStations.Station> viaStations = resolveViaStations(body.getViaCodes(), body.getViaCode(), originSt, destSt);
        String viaCodesJoined = viaStations.stream().map(KtxStations.Station::code).collect(Collectors.joining(","));
        String viaNamesJoined = viaStations.stream().map(KtxStations.Station::name).collect(Collectors.joining(","));

        // 미리보기: 픽업(origin) → 경유 → 도착
        Map<String, Object> previewNavi = kakaoNaviService.directions(originSt, destSt, viaStations);
        double extraDistance = previewNavi.get("distanceKm") != null
                ? Math.max(5.0, ((Number) previewNavi.get("distanceKm")).doubleValue() * 0.12)
                : 25.5;
        extraDistance = Math.round(extraDistance * 10.0) / 10.0;
        int extraFuelCost = calculationService.calculateExtraFuelCost(extraDistance);
        int proposedFee = body.getFee() > 0 ? body.getFee() : selected.size() * 1500;
        int netProfit = proposedFee - extraFuelCost;
        double esgReduction = calculationService.calculateEsgReduction(120.0);

        logs.add("[5] 추가 연비 산출(예상): +" + extraDistance + "km / 연료비 " + extraFuelCost + "원");
        logs.add("[6] 제안 요금 " + proposedFee + "원 → 예상 순수익 " + netProfit + "원");
        logs.add("[7] ESG 예상 절감 " + esgReduction + "kg");

        boolean matched = !eligible.isEmpty();
        double sampleRemaining = eligible.isEmpty()
                ? (trucks.isEmpty() || trucks.get(0).getRemainingVolumePercent() == null
                    ? 100.0 : trucks.get(0).getRemainingVolumePercent())
                : (eligible.get(0).getRemainingVolumePercent() != null
                    ? eligible.get(0).getRemainingVolumePercent() : 100.0);
        double baselineOccupied = 100.0 - sampleRemaining;
        double fillOfRemaining = calculationService.calculateFillOfRemaining(totalVolumeM3, sampleRemaining);

        List<Map<String, Object>> eligibleDrivers = eligible.stream().map(t -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("truckId", t.getId());
            m.put("driverName", t.getDriverName());
            m.put("truckNumber", t.getTruckNumber());
            m.put("remainingVolumePercent", t.getRemainingVolumePercent());
            return m;
        }).toList();

        if (matched) {
            String names = eligible.stream().map(Truck::getDriverName).collect(Collectors.joining(", "));
            logs.add("[4] 잔여공간 충족 기사 " + eligible.size() + "명에게 알림: " + names);
            logs.add("[4-1] 요청 적재율 " + needFill + "% / 샘플 잔여 대비 " + fillOfRemaining + "%");
        } else {
            logs.add("[4] 여유 차량 없음 → 요청만 등록, 기사 알림 없음");
        }

        String viaBrief = viaStations.isEmpty() ? "" : (" (경유 " + viaNamesJoined + ")");
        String briefing = matched
                ? (originSt.name() + " 픽업" + viaBrief + " 후 " + destSt.name()
                + " · 약 " + previewNavi.getOrDefault("durationMin", 25)
                + "분 · 순이익 약 " + String.format("%,d", netProfit) + "원 — 선착순 수락입니다.")
                : ("외부 체적 요청이 등록되었습니다. 현재 잔여공간에 맞는 차량이 없어 기사 알림은 보내지 않았습니다.");

        try {
            if (matched) {
                Map<String, Object> briefingReq = Map.of(
                        "profit", netProfit,
                        "extra_distance", extraDistance,
                        "extra_time", previewNavi.getOrDefault("durationMin", 25),
                        "esg", esgReduction
                );
                Map briefingRes = restTemplate.postForObject(
                        "http://backend-ai:8000/ai/generate-briefing", briefingReq, Map.class);
                if (briefingRes != null && briefingRes.get("briefing") != null) {
                    briefing = briefingRes.get("briefing").toString();
                    logs.add("[8] Vertex AI 브리핑 생성 완료");
                }
            }
        } catch (Exception e) {
            logs.add("[8] Vertex AI 호출 대기 → 기본 브리핑 사용");
        }

        CargoRequest saved = cargoRequestRepository.save(CargoRequest.builder()
                .origin(originSt.name())
                .destination(destSt.name())
                .viaStation(viaNamesJoined.isBlank() ? null : viaNamesJoined)
                .originCode(originSt.code())
                .destinationCode(destSt.code())
                .viaCode(viaCodesJoined.isBlank() ? null : viaCodesJoined)
                .boxCount(selected.size())
                .totalVolumeM3(totalVolumeM3)
                .totalWeightKg(totalWeightKg)
                .proposedFee(proposedFee)
                .expectedFillPercent(fillPercentOf11t)
                .baselineOccupiedPercent(baselineOccupied)
                .groupId(selectedGroupId)
                .status(matched ? "PENDING" : "UNMATCHED")
                .createdAt(LocalDateTime.now())
                .build());

        logs.add("[9] 외부 체적 요청 등록 완료 (ID: " + saved.getId() + ", status=" + saved.getStatus() + ")");
        if (!viaStations.isEmpty()) {
            logs.add("[9-1] 경유 " + viaStations.size() + "곳: " + viaNamesJoined);
        }

        String routeLabel = originSt.name()
                + (viaStations.isEmpty() ? "" : " → " + viaStations.stream().map(KtxStations.Station::name).collect(Collectors.joining(" → ")))
                + " → " + destSt.name();

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("registered", true);
        response.put("matched", matched);
        response.put("requestId", saved.getId());
        response.put("eligibleCount", eligible.size());
        response.put("eligibleDrivers", eligibleDrivers);
        response.put("origin", originSt.name());
        response.put("destination", destSt.name());
        response.put("originCode", originSt.code());
        response.put("destinationCode", destSt.code());
        response.put("viaCodes", viaStations.stream().map(KtxStations.Station::code).toList());
        response.put("viaNames", viaStations.stream().map(KtxStations.Station::name).toList());
        response.put("boxCount", selected.size());
        response.put("groupId", selectedGroupId);
        response.put("totalVolumeM3", totalVolumeM3);
        response.put("truckCapacityM3", CalculationService.TRUCK_CAPACITY_M3_11T);
        response.put("fillPercentOf11t", fillPercentOf11t);
        response.put("fillOfRemainingPercent", fillOfRemaining);
        response.put("extraDistanceKm", extraDistance);
        response.put("extraFuelCost", extraFuelCost);
        response.put("proposedFee", proposedFee);
        response.put("netProfit", netProfit);
        response.put("esgReductionKg", esgReduction);
        response.put("briefing", briefing);
        response.put("route", routeLabel);
        response.put("message", matched
                ? ("잔여공간 있는 기사 " + eligible.size() + "명에게 알림했습니다. 먼저 수락한 기사에게 배차됩니다.")
                : "체적 요청은 등록됐지만, 잔여공간이 부족해 기사에게 제안하지 않았습니다.");
        response.put("logs", logs);
        return response;
    }

    private KtxStations.Station resolveStation(String code, String name, String defaultCode) {
        if (code != null && !code.isBlank()) {
            Optional<TerminalRegistryService.Terminal> term = terminalRegistry.findByCode(code);
            if (term.isPresent()) return term.get().asStation();
            Optional<KtxStations.Station> byCode = KtxStations.findByCode(code);
            if (byCode.isPresent()) return byCode.get();
        }
        if (name != null && !name.isBlank()) {
            Optional<KtxStations.Station> byName = KtxStations.findByNameContains(name);
            if (byName.isPresent()) return byName.get();
            for (TerminalRegistryService.Terminal t : terminalRegistry.listTerminals()) {
                if (t.name() != null && t.name().contains(name.replace(" ", ""))) {
                    return t.asStation();
                }
            }
        }
        return terminalRegistry.findByCode(defaultCode)
                .map(TerminalRegistryService.Terminal::asStation)
                .or(() -> KtxStations.findByCode(defaultCode))
                .orElseGet(() -> terminalRegistry.listTerminals().isEmpty()
                        ? KtxStations.all().get(0)
                        : terminalRegistry.listTerminals().get(0).asStation());
    }

    /** 경유 역 최대 4개 (출발/도착 제외, 중복 제거) */
    private List<KtxStations.Station> resolveViaStations(
            List<String> viaCodes,
            String legacyViaCode,
            KtxStations.Station origin,
            KtxStations.Station dest
    ) {
        List<String> codes = new ArrayList<>();
        if (viaCodes != null) {
            for (String c : viaCodes) {
                if (c != null && !c.isBlank()) codes.add(c.trim());
            }
        }
        if (legacyViaCode != null && !legacyViaCode.isBlank()) {
            for (String c : legacyViaCode.split("[,|]")) {
                if (c != null && !c.isBlank()) codes.add(c.trim());
            }
        }
        LinkedHashSet<String> seen = new LinkedHashSet<>();
        List<KtxStations.Station> out = new ArrayList<>();
        for (String code : codes) {
            if (out.size() >= 4) break;
            if (origin != null && code.equalsIgnoreCase(origin.code())) continue;
            if (dest != null && code.equalsIgnoreCase(dest.code())) continue;
            if (!seen.add(code.toUpperCase(Locale.ROOT))) continue;
            KtxStations.findByCode(code).ifPresent(out::add);
        }
        return out;
    }

    /**
     * 기사 현재지 → (픽업) → 등록 경유들 → 도착.
     * 카카오 waypoints 최대 5개.
     */
    private List<KtxStations.Station> buildDriveWaypoints(
            KtxStations.Station start,
            KtxStations.Station pickup,
            KtxStations.Station dest,
            List<KtxStations.Station> vias
    ) {
        List<KtxStations.Station> waypoints = new ArrayList<>();
        Set<String> used = new LinkedHashSet<>();
        used.add(start.code().toUpperCase(Locale.ROOT));
        used.add(dest.code().toUpperCase(Locale.ROOT));

        if (pickup != null
                && used.add(pickup.code().toUpperCase(Locale.ROOT))) {
            waypoints.add(pickup);
        }
        if (vias != null) {
            for (KtxStations.Station v : vias) {
                if (waypoints.size() >= 5) break;
                if (v == null) continue;
                if (!used.add(v.code().toUpperCase(Locale.ROOT))) continue;
                waypoints.add(v);
            }
        }
        return waypoints;
    }

    @PostMapping("/{id}/accept")
    @Transactional
    public Map<String, Object> accept(@PathVariable Long id, @RequestBody(required = false) AcceptRequestDto body) {
        Long truckId = body != null && body.getTruckId() != null ? body.getTruckId() : 1L;
        Truck truck = truckRepository.findById(truckId)
                .orElseThrow(() -> new NoSuchElementException("차량 없음: " + truckId));

        double rem = truck.getRemainingVolumePercent() != null ? truck.getRemainingVolumePercent() : 100.0;
        if (body != null && body.getRemainingPercent() != null) {
            rem = body.getRemainingPercent();
        }
        CargoRequest peek = cargoRequestRepository.findById(id)
                .orElseThrow(() -> new NoSuchElementException("요청 없음"));
        double need = peek.getExpectedFillPercent() != null ? peek.getExpectedFillPercent() : 0;
        if (body != null && body.getFillPercent() != null) {
            need = body.getFillPercent();
        }
        if (rem + 0.01 < need) {
            Map<String, Object> res = new LinkedHashMap<>();
            res.put("status", "INSUFFICIENT_SPACE");
            res.put("message", "잔여공간이 부족하여 수락할 수 없습니다.");
            return res;
        }

        int updated = cargoRequestRepository.assignIfPending(id, truck.getId(), truck.getDriverName());
        if (updated == 0) {
            CargoRequest current = cargoRequestRepository.findById(id).orElse(peek);
            Map<String, Object> res = new LinkedHashMap<>();
            res.put("status", "ALREADY_ASSIGNED");
            res.put("message", "이미 배차되었습니다.");
            res.put("assignedTruckId", current.getAssignedTruckId());
            res.put("assignedDriverName", current.getAssignedDriverName());
            return res;
        }

        CargoRequest req = cargoRequestRepository.findById(id)
                .orElseThrow(() -> new NoSuchElementException("요청 없음"));

        truck.setBaselineOccupiedPercent(100.0 - rem);
        truck.setExpectedAddedFillPercent(req.getExpectedFillPercent());
        truck.setActiveRequestId(req.getId());
        truck.setStatus("MOVING");
        truckRepository.save(truck);

        // 기사 설정 출발지(없으면 부산) → 픽업 → 경유 → 목적
        KtxStations.Station start = resolveStation(truck.getOriginCode(), truck.getOriginName(), "BUSAN");
        KtxStations.Station pickup = resolveStation(req.getOriginCode(), req.getOrigin(), "BUSAN");
        KtxStations.Station dest = resolveStation(req.getDestinationCode(), req.getDestination(), "SEOUL");
        List<KtxStations.Station> vias = resolveViaStations(null, req.getViaCode(), pickup, dest);
        List<KtxStations.Station> waypoints = buildDriveWaypoints(start, pickup, dest, vias);

        Map<String, Object> navi = kakaoNaviService.directions(start, dest, waypoints);

        double extraKm = navi.get("distanceKm") != null
                ? ((Number) navi.get("distanceKm")).doubleValue() * 0.12
                : 25.5;
        extraKm = Math.round(extraKm * 10.0) / 10.0;
        int expense = calculationService.calculateExtraFuelCost(extraKm);
        int income = req.getProposedFee() != null ? req.getProposedFee() : 0;
        int net = income - expense;
        double esg = calculationService.calculateEsgReduction(120.0);

        List<String> routeParts = new ArrayList<>();
        routeParts.add(start.name());
        for (KtxStations.Station w : waypoints) routeParts.add(w.name());
        routeParts.add(dest.name());
        String routeLabel = String.join(" → ", routeParts);

        loadHistoryRepository.save(LoadHistory.builder()
                .truckId(truck.getId())
                .cargoRequestId(req.getId())
                .origin(req.getOrigin())
                .destination(req.getDestination())
                .routeSummary(routeLabel)
                .loadImageUrl("DISPATCH-" + req.getId())
                .remainingVolumePercent(truck.getRemainingVolumePercent())
                .occupiedVolumePercent(0.0)
                .esgReductionKg(esg)
                .income(income)
                .expense(expense)
                .netProfit(net)
                .createdAt(LocalDateTime.now())
                .build());

        List<Map<String, Object>> stops = new ArrayList<>();
        stops.add(stationStop(start, "출발"));
        for (KtxStations.Station w : waypoints) stops.add(stationStop(w, "경유"));
        stops.add(stationStop(dest, "도착"));

        // 시연: 수락·출발 후 OD 그룹을 다음 출도착으로 이동 → 복화리스트에 다시 노출
        Map<String, Object> advanced = Map.of();
        boolean skipAdvance = body != null && Boolean.TRUE.equals(body.getSkipOdAdvance());
        if (!skipAdvance) {
            try {
                advanced = cargoOdGroupService.advanceAfterAccept(
                        req.getId(),
                        truck.getDestinationCode() != null ? truck.getDestinationCode() : "SEOUL"
                );
            } catch (Exception ignored) {
                advanced = Map.of("advanced", false, "reason", "skip");
            }
        } else {
            advanced = Map.of("advanced", false, "reason", "batch-skip");
        }

        Map<String, Object> res = new LinkedHashMap<>();
        res.put("status", "ASSIGNED");
        res.put("message", truck.getDriverName() + " 수락 (정산 +1건): " + routeLabel);
        res.put("truckId", truck.getId());
        res.put("driverName", truck.getDriverName());
        res.putAll(navi);
        res.put("stops", stops);
        res.put("expectedFillPercent", req.getExpectedFillPercent());
        res.put("baselineOccupiedPercent", truck.getBaselineOccupiedPercent());
        res.put("odAdvance", advanced);
        if (advanced.get("message") != null) {
            res.put("message", res.get("message") + " · " + advanced.get("message"));
        }
        res.put("ledgerAdded", Map.of(
                "origin", req.getOrigin() != null ? req.getOrigin() : "",
                "destination", req.getDestination() != null ? req.getDestination() : "",
                "route", routeLabel,
                "income", income,
                "expense", expense,
                "netProfit", net,
                "esg", esg
        ));
        return res;
    }

    private Map<String, Object> stationStop(KtxStations.Station s, String role) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("code", s.code());
        m.put("name", s.name());
        m.put("role", role);
        m.put("lat", s.lat());
        m.put("lng", s.lng());
        return m;
    }

    /** 거절은 해당 기사 화면에서만 닫힘 — 다른 기사는 계속 수락 가능 */
    @PostMapping("/{id}/reject")
    public Map<String, Object> reject(@PathVariable Long id, @RequestBody(required = false) AcceptRequestDto body) {
        CargoRequest req = cargoRequestRepository.findById(id)
                .orElseThrow(() -> new NoSuchElementException("요청 없음"));
        if ("ASSIGNED".equals(req.getStatus())) {
            return Map.of(
                    "status", "ALREADY_ASSIGNED",
                    "message", "이미 배차되었습니다.",
                    "assignedDriverName", req.getAssignedDriverName() != null ? req.getAssignedDriverName() : ""
            );
        }
        Long truckId = body != null ? body.getTruckId() : null;
        return Map.of(
                "status", "DISMISSED",
                "message", "이 제안은 닫았습니다. 다른 기사님은 계속 수락할 수 있습니다.",
                "requestId", id,
                "truckId", truckId != null ? truckId : 0
        );
    }

    @GetMapping("/drivers")
    public Map<String, Object> drivers() {
        List<Map<String, Object>> list = truckRepository.findAll().stream().map(this::truckToMap).toList();
        return Map.of("drivers", list, "count", list.size());
    }

    /**
     * 기존 matching 체적 → cargo_od_groups 테이블로 OD 그룹 적재 (1회성 스냅샷).
     * force=true 이면 비어 있지 않아도 다시 빌드.
     */
    @PostMapping("/sync-admin-cargos")
    public Map<String, Object> syncAdminCargos(
            @RequestParam(required = false) Long truckId,
            @RequestParam(defaultValue = "false") boolean force
    ) {
        String originCode = "BUSAN";
        if (truckId != null) {
            Truck truck = truckRepository.findById(truckId).orElse(null);
            if (truck != null && truck.getOriginCode() != null) {
                originCode = truck.getOriginCode();
            }
        }
        if (!force) {
            return adminCargoBridgeService.ensureOdGroupsBuilt(originCode);
        }
        return adminCargoBridgeService.buildOdGroups(originCode, 500);
    }

    /** OD 그룹 테이블 조회 (복화 원천 데이터) */
    @GetMapping("/od-groups")
    public Map<String, Object> listOdGroups() {
        var list = adminCargoBridgeService.listOdGroups();
        return Map.of("groups", list, "count", list.size());
    }

    /**
     * 단건 운송장/박스 등록 → 출도착 기준 OD 그룹에 자동 합류.
     * 관리자·시연 모달에서 한 건씩 넣을 때 사용.
     */
    @PostMapping("/od-items")
    public Map<String, Object> registerOdItem(@RequestBody Map<String, Object> body) {
        String oTerm = strOrNull(body.get("originTerminalCode"));
        String dTerm = strOrNull(body.get("destinationTerminalCode"));
        String oSt = strOrNull(body.get("originStationCode"));
        String dSt = strOrNull(body.get("destinationStationCode"));
        if (oTerm == null) oTerm = oSt;
        if (dTerm == null) dTerm = dSt;
        try {
            CargoOdGroupService.RegisterItemRequest req = new CargoOdGroupService.RegisterItemRequest(
                    strOrNull(body.get("externalCargoId")),
                    oTerm,
                    dTerm,
                    strOrNull(body.get("originTerminalName")),
                    strOrNull(body.get("destinationTerminalName")),
                    intOrNull(body.get("boxCount")),
                    doubleOrNull(body.get("volumeM3")),
                    doubleOrNull(body.get("weightKg")),
                    intOrNull(body.get("freightKrw")),
                    strOrNull(body.get("productCode")),
                    strOrNull(body.get("productName")),
                    oSt,
                    dSt,
                    strOrNull(body.get("photoUrl"))
            );
            return cargoOdGroupService.registerItem(req);
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage());
        }
    }

    /** 체적(m³) → 3/5/11/18톤 등 표준 차종 점유율 미리보기 */
    @GetMapping("/fill-preview")
    public Map<String, Object> fillPreview(@RequestParam double volumeM3) {
        return calculationService.fillPreview(Math.max(0, volumeM3));
    }

    /** 그룹에 속한 박스(운송장) 목록 — 복화카드 「목록」 버튼 */
    @GetMapping("/od-groups/{id}/items")
    public Map<String, Object> listOdGroupItems(
            @PathVariable Long id,
            @RequestParam(defaultValue = "500") int limit
    ) {
        var group = cargoOdGroupService.findGroup(id)
                .orElseThrow(() -> new NoSuchElementException("OD 그룹 없음: " + id));
        List<CargoOdItem> items = cargoOdGroupService.listItems(id);
        int lim = Math.min(Math.max(limit, 1), 500);
        List<Map<String, Object>> rows = new ArrayList<>();
        for (CargoOdItem it : items) {
            if (rows.size() >= lim) break;
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", it.getId());
            m.put("externalCargoId", it.getExternalCargoId());
            m.put("originTerminalCode", it.getOriginTerminalCode());
            m.put("destinationTerminalCode", it.getDestinationTerminalCode());
            m.put("boxCount", it.getBoxCount());
            m.put("volumeM3", it.getVolumeM3());
            m.put("weightKg", it.getWeightKg());
            m.put("freightKrw", it.getFreightKrw());
            m.put("productCode", it.getProductCode());
            m.put("productName", it.getProductName());
            m.put("photoUrl", it.getPhotoUrl());
            m.put("status", it.getStatus());
            m.put("createdAt", it.getCreatedAt() != null ? it.getCreatedAt().toString() : null);
            rows.add(m);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("odGroupId", group.getId());
        out.put("routeKey", group.getRouteKey());
        out.put("origin", group.getOriginTerminalName());
        out.put("destination", group.getDestinationTerminalName());
        out.put("waybillCount", group.getWaybillCount());
        out.put("boxCount", group.getBoxCount());
        out.put("volumeM3", group.getVolumeM3());
        out.put("productSummary", group.getProductSummary());
        out.put("photoUrl", group.getPhotoUrl());
        out.put("items", rows);
        out.put("count", rows.size());
        out.put("totalItems", items.size());
        out.put("aggregateOnly", rows.isEmpty() && (group.getWaybillCount() != null && group.getWaybillCount() > 0));
        return out;
    }

    /** 시연용 부산→서울 축 OD 그룹 배치 (~10터미널, ~20그룹, 그룹당 100~500건) */
    @PostMapping("/seed-demo-corridor")
    public Map<String, Object> seedDemoCorridor(
            @RequestParam(defaultValue = "true") boolean clear
    ) {
        return demoOdSeedService.seedBusanSeoulCorridor(clear);
    }

    /**
     * 지도에서 터미널 선택 시: 해당 터미널 출발 OD 그룹 5건 페이징.
     * 거리/카카오 계산 없음 (목록 응답 속도 우선).
     */
    @GetMapping("/groups-by-terminal")
    public Map<String, Object> groupsByTerminal(
            @RequestParam Long truckId,
            @RequestParam String terminalCode,
            @RequestParam(defaultValue = "0") int page
    ) {
        Truck truck = truckRepository.findById(truckId)
                .orElseThrow(() -> new NoSuchElementException("차량 없음: " + truckId));
        double rem = truck.getRemainingVolumePercent() != null ? truck.getRemainingVolumePercent() : 100.0;

        String code = terminalCode.trim();
        List<com.moveai.backend.entity.CargoOdGroup> matched = new ArrayList<>();
        for (com.moveai.backend.entity.CargoOdGroup g : adminCargoBridgeService.listOdGroups()) {
            if (g.getWaybillCount() == null || g.getWaybillCount() <= 0) continue;
            boolean originHit = code.equalsIgnoreCase(g.getOriginTerminalCode())
                    || code.equalsIgnoreCase(g.getOriginStationCode());
            if (!originHit) continue;
            if (g.getCargoRequestId() == null) continue;
            CargoRequest req = cargoRequestRepository.findById(g.getCargoRequestId()).orElse(null);
            if (req == null || !"PENDING".equals(req.getStatus())) continue;
            double need = calculationService.resolveFillForTruck(g.getVolumeM3(), g.getFillByVehicleJson(), truck);
            if (need <= 0 && g.getFillPercentOf11t() != null) need = g.getFillPercentOf11t();
            if (rem + 0.01 < need) continue;
            matched.add(g);
        }
        matched.sort(Comparator.comparingLong(g -> g.getId() != null ? g.getId() : 0L));

        int size = 5;
        int from = Math.max(0, page) * size;
        int to = Math.min(from + size, matched.size());
        List<Map<String, Object>> items = new ArrayList<>();
        if (from < matched.size()) {
            for (com.moveai.backend.entity.CargoOdGroup g : matched.subList(from, to)) {
                CargoRequest req = cargoRequestRepository.findById(g.getCargoRequestId()).orElse(null);
                if (req == null) continue;
                int fee = g.getFreightKrw() != null ? g.getFreightKrw() : 0;
                double fill = calculationService.resolveFillForTruck(g.getVolumeM3(), g.getFillByVehicleJson(), truck);
                Map<String, Object> m = buildCargoCard(req,
                        new RouteMatchService.RouteMetrics(true, 0, 0, 0, 1),
                        fee, 0, fee, 0, rem);
                m.put("odGroupId", g.getId());
                m.put("routeKey", g.getRouteKey());
                m.put("waybillCount", g.getWaybillCount());
                m.put("boxCount", g.getBoxCount());
                m.put("volumeM3", g.getVolumeM3());
                m.put("fillPercent", fill);
                m.put("fillPercentOf11t", g.getFillPercentOf11t());
                m.put("fillByVehicle", calculationService.parseFillByVehicleJson(g.getFillByVehicleJson()));
                m.put("productSummary", g.getProductSummary());
                m.put("photoUrl", g.getPhotoUrl());
                m.put("source", "cargo_od_groups");
                items.add(m);
            }
        }

        var term = terminalRegistry.findByCode(code).orElse(null);
        Map<String, Object> res = new LinkedHashMap<>();
        res.put("terminalCode", code);
        res.put("terminalName", term != null ? term.name() : code);
        res.put("terminalLat", term != null ? term.lat() : null);
        res.put("terminalLng", term != null ? term.lng() : null);
        res.put("items", items);
        res.put("count", items.size());
        res.put("page", page);
        res.put("pageSize", size);
        res.put("hasMore", to < matched.size());
        res.put("candidateCount", matched.size());
        res.put("mode", "manual");
        return res;
    }

    /**
     * 장바구니 미리보기: 담은 OD를 기사 O→D에 합쳐 경로·직행 대비 증분 km 반환.
     */
    @PostMapping("/preview-cart")
    public Map<String, Object> previewCart(@RequestBody CartPreviewDto body) {
        if (body.getTruckId() == null) throw new IllegalArgumentException("truckId 필요");
        Truck truck = truckRepository.findById(body.getTruckId())
                .orElseThrow(() -> new NoSuchElementException("차량 없음"));
        List<Long> ids = body.getOdGroupIds() != null ? body.getOdGroupIds() : List.of();
        return dispatchCartService.preview(truck, ids);
    }

    /** 운행 중 경유를 끼운 뒤 도로 폴리라인만 재계산 */
    @PostMapping("/restitch-route")
    @SuppressWarnings("unchecked")
    public Map<String, Object> restitchRoute(@RequestBody Map<String, Object> body) {
        Object raw = body != null ? body.get("stops") : null;
        List<Map<String, Object>> stops = new ArrayList<>();
        if (raw instanceof List<?> list) {
            for (Object o : list) {
                if (o instanceof Map<?, ?> m) {
                    Map<String, Object> row = new LinkedHashMap<>();
                    m.forEach((k, v) -> row.put(String.valueOf(k), v));
                    stops.add(row);
                }
            }
        }
        return dispatchCartService.restitchFromStops(stops);
    }

    /**
     * 수락/상세 직전: 행렬 기반 우회거리 1건.
     * 목록에는 호출하지 않음. 경유지가 붙을 때 증분 측정용.
     */
    @GetMapping("/estimate-detour")
    public Map<String, Object> estimateDetour(
            @RequestParam Long truckId,
            @RequestParam Long odGroupId,
            @RequestParam(required = false) List<String> waypoints
    ) {
        Truck truck = truckRepository.findById(truckId)
                .orElseThrow(() -> new NoSuchElementException("차량 없음: " + truckId));
        com.moveai.backend.entity.CargoOdGroup group = cargoOdGroupService.findGroup(odGroupId)
                .orElseThrow(() -> new NoSuchElementException("OD 그룹 없음: " + odGroupId));

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("odGroupId", odGroupId);
        out.put("routeKey", group.getRouteKey());
        out.put("originCode", group.getOriginTerminalCode());
        out.put("destinationCode", group.getDestinationTerminalCode());

        double fill = calculationService.resolveFillForTruck(group.getVolumeM3(), group.getFillByVehicleJson(), truck);
        out.put("fillPercent", fill);
        out.put("fillByVehicle", calculationService.parseFillByVehicleJson(group.getFillByVehicleJson()));

        if (waypoints != null && !waypoints.isEmpty()
                && truck.getOriginCode() != null && truck.getDestinationCode() != null
                && group.getOriginTerminalCode() != null && group.getDestinationTerminalCode() != null) {
            var det = terminalDistanceMatrixService.incrementalWithWaypoints(
                    truck.getOriginCode(),
                    waypoints,
                    group.getOriginTerminalCode(),
                    group.getDestinationTerminalCode(),
                    truck.getDestinationCode()
            );
            out.put("baseKm", det.baseKm());
            out.put("viaKm", det.viaKm());
            out.put("extraDistanceKm", det.extraKm());
            out.put("extraMinutes", det.extraMinutes());
            out.put("distanceSource", det.source());
            out.put("mode", "incremental");
        } else {
            OdDetourService.Candidate c = odDetourService.estimateOne(truck, group);
            double extra = c.roadExtraKm() != null ? c.roadExtraKm() : 0;
            int fuel = calculationService.calculateExtraFuelCost(extra);
            int fee = group.getFreightKrw() != null ? group.getFreightKrw() : 0;
            out.put("extraDistanceKm", extra);
            out.put("extraMinutes", c.extraMinutes() != null ? c.extraMinutes() : Math.round(extra));
            out.put("extraFuelCost", fuel);
            out.put("netProfit", fee - fuel);
            out.put("distanceSource", c.distanceSource());
            out.put("mode", "od");
        }
        return out;
    }

    /** 시연축 터미널 N×N 거리 행렬 warm */
    @PostMapping("/warm-distance-matrix")
    public Map<String, Object> warmDistanceMatrix(@RequestParam(required = false) List<String> codes) {
        List<String> list = codes != null && !codes.isEmpty()
                ? codes
                : terminalRegistry.listTerminals().stream().map(TerminalRegistryService.Terminal::code).limit(12).toList();
        return terminalDistanceMatrixService.warmCodes(list);
    }

    /** 물량(PENDING OD 그룹)이 있는 출발 터미널만 */
    @GetMapping("/terminals-with-cargo")
    public Map<String, Object> terminalsWithCargo(@RequestParam(required = false) Long truckId) {
        // ensureOdGroupsBuilt(admin sync) 는 시연 시드를 건드리지 않도록 여기서 호출하지 않음

        Map<String, Integer> waybillCounts = new LinkedHashMap<>();
        Map<String, Integer> groupCounts = new LinkedHashMap<>();
        for (com.moveai.backend.entity.CargoOdGroup g : adminCargoBridgeService.listOdGroups()) {
            if (g.getWaybillCount() == null || g.getWaybillCount() <= 0) continue;
            if (g.getCargoRequestId() == null) continue;
            CargoRequest req = cargoRequestRepository.findById(g.getCargoRequestId()).orElse(null);
            if (req == null || !"PENDING".equals(req.getStatus())) continue;
            String code = g.getOriginTerminalCode();
            if (code == null || code.isBlank()) code = g.getOriginStationCode();
            if (code == null || code.isBlank()) continue;
            waybillCounts.merge(code, g.getWaybillCount() != null ? g.getWaybillCount() : 1, Integer::sum);
            groupCounts.merge(code, 1, Integer::sum);
        }

        List<Map<String, Object>> list = new ArrayList<>();
        for (Map.Entry<String, Integer> e : waybillCounts.entrySet()) {
            var term = terminalRegistry.findByCode(e.getKey()).orElse(null);
            Double lat = term != null ? term.lat() : null;
            Double lng = term != null ? term.lng() : null;
            String name = term != null ? term.name() : e.getKey();
            String address = term != null ? term.address() : "";
            // 레지스트리 GPS 없으면 OD 그룹 좌표 폴백 (시드 터미널 누락 방지)
            if (lat == null || lat == 0 || lng == null || lng == 0) {
                for (com.moveai.backend.entity.CargoOdGroup g : adminCargoBridgeService.listOdGroups()) {
                    String oc = g.getOriginTerminalCode() != null ? g.getOriginTerminalCode() : g.getOriginStationCode();
                    if (e.getKey().equalsIgnoreCase(oc) && g.getOriginLat() != null && g.getOriginLng() != null) {
                        lat = g.getOriginLat();
                        lng = g.getOriginLng();
                        if (g.getOriginTerminalName() != null) name = g.getOriginTerminalName();
                        break;
                    }
                }
            }
            if (lat == null || lng == null || lat == 0) continue;
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("code", e.getKey());
            m.put("name", name);
            m.put("address", address);
            m.put("lat", lat);
            m.put("lng", lng);
            m.put("waybillCount", e.getValue());
            m.put("groupCount", groupCounts.getOrDefault(e.getKey(), 0));
            m.put("hasCargo", true);
            list.add(m);
        }
        // 코드 정렬 (숫자 코드 우선)
        list.sort(Comparator.comparing(m -> String.valueOf(m.get("code"))));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("terminals", list);
        out.put("count", list.size());
        return out;
    }

    /**
     * 시연: 현재 위치 반경 안, 기사 도착지와 같고 잔여공간에 들어가는 PENDING 물량.
     */
    @GetMapping("/nearby-loadable")
    public Map<String, Object> nearbyLoadable(
            @RequestParam Long truckId,
            @RequestParam double lat,
            @RequestParam double lng,
            @RequestParam(defaultValue = "20") double radiusKm,
            @RequestParam(required = false) Double remainingPercent,
            @RequestParam(required = false) String destinationCode
    ) {
        Truck truck = truckRepository.findById(truckId)
                .orElseThrow(() -> new NoSuchElementException("차량 없음: " + truckId));
        double rem = remainingPercent != null
                ? remainingPercent
                : (truck.getRemainingVolumePercent() != null ? truck.getRemainingVolumePercent() : 100.0);
        if (rem < 0) rem = 0;
        if (rem < 0.5) {
            Map<String, Object> empty = new LinkedHashMap<>();
            empty.put("remainingPercent", Math.round(rem * 10.0) / 10.0);
            empty.put("destinationCode", destinationCode != null ? destinationCode : "");
            empty.put("radiusKm", radiusKm);
            empty.put("terminals", List.of());
            empty.put("count", 0);
            return empty;
        }
        String dest = destinationCode != null && !destinationCode.isBlank()
                ? destinationCode.trim()
                : (truck.getDestinationCode() != null ? truck.getDestinationCode().trim() : "");
        if (dest.isBlank() || dest.regionMatches(true, 0, "stop-", 0, 5) || dest.regionMatches(true, 0, "via-", 0, 4)) {
            dest = truck.getDestinationCode() != null ? truck.getDestinationCode().trim() : "";
        }
        if (dest.isBlank()) {
            dest = inferDemoDest(truck.getOriginCode());
        }

        Map<String, Map<String, Object>> byOrigin = new LinkedHashMap<>();
        for (com.moveai.backend.entity.CargoOdGroup g : adminCargoBridgeService.listOdGroups()) {
            if (g.getWaybillCount() == null || g.getWaybillCount() <= 0) continue;
            if (g.getCargoRequestId() == null) continue;
            CargoRequest req = cargoRequestRepository.findById(g.getCargoRequestId()).orElse(null);
            if (req == null || !"PENDING".equals(req.getStatus())) continue;
            String drop = g.getDestinationTerminalCode() != null ? g.getDestinationTerminalCode() : g.getDestinationStationCode();
            if (drop == null || drop.isBlank() || !OdDetourService.sameDestRegion(dest, drop)) continue;
            double need = calculationService.resolveFillForTruck(g.getVolumeM3(), g.getFillByVehicleJson(), truck);
            if (need <= 0 && g.getFillPercentOf11t() != null) need = g.getFillPercentOf11t();
            if (need <= 0 || rem + 0.01 < need) continue;

            String code = g.getOriginTerminalCode();
            if (code == null || code.isBlank()) code = g.getOriginStationCode();
            if (code == null || code.isBlank()) continue;
            Double oLat = g.getOriginLat();
            Double oLng = g.getOriginLng();
            String name = g.getOriginTerminalName() != null ? g.getOriginTerminalName() : code;
            var term = terminalRegistry.findByCode(code).orElse(null);
            if (term != null) {
                if (oLat == null || oLat == 0 || oLng == null || oLng == 0) {
                    oLat = term.lat();
                    oLng = term.lng();
                }
                if (term.name() != null && !term.name().isBlank()) name = term.name();
            }
            if (oLat == null || oLng == null || oLat == 0) continue;
            double dist = OdDetourService.haversineKm(lat, lng, oLat, oLng);
            if (dist > radiusKm + 0.5) continue;

            Map<String, Object> row = byOrigin.get(code);
            double fill = Math.round(need * 10.0) / 10.0;
            if (row == null || fill > ((Number) row.get("fillPercent")).doubleValue()) {
                row = new LinkedHashMap<>();
                row.put("code", code);
                row.put("name", name);
                row.put("lat", oLat);
                row.put("lng", oLng);
                row.put("fillPercent", fill);
                row.put("distanceKm", Math.round(dist * 10.0) / 10.0);
                row.put("odGroupId", g.getId());
                row.put("requestId", g.getCargoRequestId());
                row.put("origin", name);
                row.put("originCode", code);
                row.put("destination", g.getDestinationTerminalName() != null ? g.getDestinationTerminalName() : drop);
                row.put("destinationCode", drop);
                byOrigin.put(code, row);
            }
        }

        List<Map<String, Object>> terminals = new ArrayList<>(byOrigin.values());
        terminals.sort(Comparator.comparingDouble(m -> ((Number) m.get("distanceKm")).doubleValue()));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("remainingPercent", Math.round(rem * 10.0) / 10.0);
        out.put("destinationCode", dest);
        out.put("destinationRegion", OdDetourService.destRegion(dest));
        out.put("radiusKm", radiusKm);
        out.put("terminals", terminals);
        out.put("count", terminals.size());
        return out;
    }

    /** 출도착이 비면 경부 시연 축 기본 도착(남→서울, 북→부산). */
    private static String inferDemoDest(String originCode) {
        String region = OdDetourService.destRegion(originCode);
        if ("SEOUL".equals(region)) return "200";
        return "001";
    }

    /** LLM 최적 배차 플랜 (기사 출도착 기준) */
    @PostMapping("/optimal-plan")
    public Map<String, Object> optimalPlan(@RequestBody Map<String, Object> body) {
        Long truckId = body.get("truckId") instanceof Number n ? n.longValue() : null;
        if (truckId == null) throw new IllegalArgumentException("truckId 필요");
        Truck truck = truckRepository.findById(truckId)
                .orElseThrow(() -> new NoSuchElementException("차량 없음"));
        try {
            adminCargoBridgeService.ensureOdGroupsBuilt(
                    truck.getOriginCode() != null ? truck.getOriginCode() : "200");
        } catch (Exception ignored) {}
        return optimalDispatchService.buildPlan(truck);
    }

    /** 일괄 수락 — requestIds 순서대로 배정 */
    @PostMapping("/accept-batch")
    @Transactional
    public Map<String, Object> acceptBatch(@RequestBody BatchAcceptDto body) {
        if (body.getTruckId() == null || body.getRequestIds() == null || body.getRequestIds().isEmpty()) {
            throw new IllegalArgumentException("truckId와 requestIds 필요");
        }
        Truck truck = truckRepository.findById(body.getTruckId())
                .orElseThrow(() -> new NoSuchElementException("차량 없음"));
        List<Map<String, Object>> results = new ArrayList<>();
        List<Long> accepted = new ArrayList<>();
        List<Long> failed = new ArrayList<>();
        AcceptRequestDto single = new AcceptRequestDto();
        single.setTruckId(body.getTruckId());
        single.setSkipOdAdvance(true);

        Map<String, Object> lastOk = null;
        for (Long id : body.getRequestIds()) {
            try {
                Map<String, Object> one = accept(id, single);
                String st = String.valueOf(one.get("status"));
                if ("ASSIGNED".equals(st)) {
                    accepted.add(id);
                    lastOk = one;
                    results.add(Map.of("requestId", id, "status", "ASSIGNED"));
                } else {
                    failed.add(id);
                    results.add(Map.of("requestId", id, "status", st,
                            "message", String.valueOf(one.getOrDefault("message", ""))));
                }
            } catch (Exception e) {
                failed.add(id);
                results.add(Map.of("requestId", id, "status", "ERROR", "message", e.getMessage()));
            }
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", accepted.isEmpty() ? "NONE" : "BATCH_ASSIGNED");
        out.put("accepted", accepted);
        out.put("failed", failed);
        out.put("count", accepted.size());
        out.put("results", results);
        out.put("message", "일괄 수락 " + accepted.size() + "건");
        if (lastOk != null) {
            out.put("navi", lastOk);
            if (lastOk.get("path") != null) out.put("path", lastOk.get("path"));
            if (lastOk.get("stops") != null) out.put("stops", lastOk.get("stops"));
            if (lastOk.get("distanceKm") != null) out.put("distanceKm", lastOk.get("distanceKm"));
            if (lastOk.get("durationMin") != null) out.put("durationMin", lastOk.get("durationMin"));
            if (lastOk.get("naviRoute") != null) out.put("naviRoute", lastOk.get("naviRoute"));
        }
        truckRepository.findById(truck.getId()).ifPresent(t -> {
            out.put("remainingVolumePercent", t.getRemainingVolumePercent());
            out.put("statusTruck", t.getStatus());
        });
        return out;
    }

    private List<Map<String, Object>> mapCandidatesToCards(OdDetourService.PageResult pageResult, double rem) {
        List<Map<String, Object>> items = new ArrayList<>();
        for (OdDetourService.Candidate c : pageResult.pageItems()) {
            com.moveai.backend.entity.CargoOdGroup g = c.group();
            CargoRequest req = cargoRequestRepository.findById(g.getCargoRequestId()).orElse(null);
            if (req == null) continue;
            double extraKm = c.roadExtraKm() != null ? c.roadExtraKm() : c.straightExtraKm();
            int fee = g.getFreightKrw() != null ? g.getFreightKrw() : 0;
            int extraFuelCost = calculationService.calculateExtraFuelCost(extraKm);
            int net = fee - extraFuelCost;
            double cargoLegKm = 5.0;
            if (g.getOriginLat() != null && g.getDestinationLat() != null) {
                cargoLegKm = routeMatchService.haversine(
                        g.getOriginLat(), g.getOriginLng(),
                        g.getDestinationLat(), g.getDestinationLng());
            }
            double esg = calculationService.calculateEsgReduction(cargoLegKm);
            RouteMatchService.RouteMetrics metrics = new RouteMatchService.RouteMetrics(
                    true, pageResult.baseKm(), pageResult.baseKm() + extraKm, extraKm,
                    pageResult.baseKm() > 0 ? (pageResult.baseKm() + extraKm) / pageResult.baseKm() : 1
            );
            Map<String, Object> m = buildCargoCard(req, metrics, fee, extraFuelCost, net, esg, rem);
            m.put("odGroupId", g.getId());
            m.put("routeKey", g.getRouteKey());
            m.put("waybillCount", g.getWaybillCount());
            m.put("pickupDistanceKm", c.pickupDistKm());
            m.put("extraDistanceKm", extraKm);
            m.put("extraMinutes", c.extraMinutes() != null ? c.extraMinutes() : Math.round(extraKm / 60.0 * 60));
            m.put("distanceSource", c.distanceSource());
            m.put("fillPercent", c.fillPercent());
            m.put("fillByVehicle", calculationService.parseFillByVehicleJson(g.getFillByVehicleJson()));
            m.put("source", "cargo_od_groups");
            items.add(m);
        }
        return items;
    }

    private static String strOrNull(Object o) {
        if (o == null) return null;
        String s = String.valueOf(o).trim();
        return s.isEmpty() ? null : s;
    }

    private static Integer intOrNull(Object o) {
        if (o == null) return null;
        if (o instanceof Number n) return n.intValue();
        try { return Integer.parseInt(String.valueOf(o).trim()); } catch (Exception e) { return null; }
    }

    private static Double doubleOrNull(Object o) {
        if (o == null) return null;
        if (o instanceof Number n) return n.doubleValue();
        try { return Double.parseDouble(String.valueOf(o).trim()); } catch (Exception e) { return null; }
    }

    /**
     * 기사 출도착 경로에 맞는 복화 리스트.
     * 출발지 근접 정렬 → 직선 예비필터 → 페이지당 5건 카카오 우회(+30km 이하).
     */
    @GetMapping("/cargo-feed")
    public Map<String, Object> cargoFeed(
            @RequestParam Long truckId,
            @RequestParam(required = false) Long sinceId,
            @RequestParam(defaultValue = "0") int page
    ) {
        Truck truck = truckRepository.findById(truckId)
                .orElseThrow(() -> new NoSuchElementException("차량 없음: " + truckId));
        double rem = truck.getRemainingVolumePercent() != null ? truck.getRemainingVolumePercent() : 100.0;
        String dO = truck.getOriginCode();
        String dD = truck.getDestinationCode();

        Map<String, Object> syncMeta = Collections.emptyMap();
        try {
            syncMeta = adminCargoBridgeService.ensureOdGroupsBuilt(dO != null ? dO : "200");
        } catch (Exception e) {
            syncMeta = Map.of("error", String.valueOf(e.getMessage()));
        }

        List<com.moveai.backend.entity.CargoOdGroup> groups = adminCargoBridgeService.listOdGroups();
        // PENDING 그룹만
        List<com.moveai.backend.entity.CargoOdGroup> pending = new ArrayList<>();
        for (com.moveai.backend.entity.CargoOdGroup g : groups) {
            Long requestId = g.getCargoRequestId();
            if (requestId == null) continue;
            CargoRequest req = cargoRequestRepository.findById(requestId).orElse(null);
            if (req == null || !"PENDING".equals(req.getStatus())) continue;
            pending.add(g);
        }

        OdDetourService.PageResult pageResult = odDetourService.pageForTruck(truck, pending, page, rem);
        List<Map<String, Object>> items = new ArrayList<>();
        List<Map<String, Object>> notifications = new ArrayList<>();

        for (OdDetourService.Candidate c : pageResult.pageItems()) {
            com.moveai.backend.entity.CargoOdGroup g = c.group();
            CargoRequest req = cargoRequestRepository.findById(g.getCargoRequestId()).orElse(null);
            if (req == null) continue;

            double extraKm = c.roadExtraKm() != null ? c.roadExtraKm() : c.straightExtraKm();
            int fee = g.getFreightKrw() != null ? g.getFreightKrw() : 0;
            int extraFuelCost = calculationService.calculateExtraFuelCost(extraKm);
            int net = fee - extraFuelCost;
            double cargoLegKm = 5.0;
            if (g.getOriginLat() != null && g.getDestinationLat() != null) {
                cargoLegKm = routeMatchService.haversine(
                        g.getOriginLat(), g.getOriginLng(),
                        g.getDestinationLat(), g.getDestinationLng());
            }
            double esg = calculationService.calculateEsgReduction(cargoLegKm);

            RouteMatchService.RouteMetrics metrics = new RouteMatchService.RouteMetrics(
                    true, pageResult.baseKm(), pageResult.baseKm() + extraKm, extraKm,
                    pageResult.baseKm() > 0 ? (pageResult.baseKm() + extraKm) / pageResult.baseKm() : 1
            );
            Map<String, Object> m = buildCargoCard(req, metrics, fee, extraFuelCost, net, esg, rem);
            m.put("odGroupId", g.getId());
            m.put("routeKey", g.getRouteKey());
            m.put("waybillCount", g.getWaybillCount());
            m.put("pickupDistanceKm", c.pickupDistKm());
            m.put("straightExtraKm", c.straightExtraKm());
            m.put("extraDistanceKm", extraKm);
            m.put("distanceSource", c.distanceSource());
            m.put("maxExtraKm", OdDetourService.MAX_EXTRA_KM);
            m.put("source", "cargo_od_groups");
            m.put("briefing", String.format(
                    "%s → %s · 운송장 %d건 · 우회 +%.1fkm · 순이익 %,d원",
                    g.getOriginTerminalName(), g.getDestinationTerminalName(),
                    g.getWaybillCount() != null ? g.getWaybillCount() : 0,
                    extraKm, net));
            items.add(m);
            Long requestId = g.getCargoRequestId();
            if (sinceId != null && requestId != null && requestId > sinceId) {
                notifications.add(m);
            }
        }

        Map<String, Object> res = new LinkedHashMap<>();
        res.put("truckId", truck.getId());
        res.put("driverName", truck.getDriverName());
        res.put("originCode", dO);
        res.put("destinationCode", dD);
        res.put("remainingVolumePercent", rem);
        res.put("items", items);
        res.put("count", items.size());
        res.put("page", pageResult.page());
        res.put("pageSize", pageResult.pageSize());
        res.put("hasMore", pageResult.hasMore());
        res.put("candidateCount", pageResult.candidateCount());
        res.put("baseDistanceKm", pageResult.baseKm());
        res.put("baseSource", pageResult.baseSource());
        res.put("notifications", notifications);
        res.put("notificationCount", notifications.size());
        res.put("odGroupMeta", syncMeta);
        return res;
    }

    /** 하위호환: offers = cargo-feed */
    @GetMapping("/offers")
    public Map<String, Object> offers(
            @RequestParam Long truckId,
            @RequestParam(defaultValue = "0") int page
    ) {
        Map<String, Object> feed = cargoFeed(truckId, null, page);
        feed.put("offers", feed.get("items"));
        return feed;
    }

    private Map<String, Object> buildCargoCard(
            CargoRequest req,
            RouteMatchService.RouteMetrics metrics,
            int fee,
            int extraFuelCost,
            int net,
            double esg,
            double rem
    ) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("requestId", req.getId());
        m.put("origin", req.getOrigin());
        m.put("destination", req.getDestination());
        m.put("originCode", req.getOriginCode());
        m.put("destinationCode", req.getDestinationCode());
        m.put("viaCodes", req.getViaCode() != null ? Arrays.asList(req.getViaCode().split(",")) : List.of());
        m.put("boxCount", req.getBoxCount());
        m.put("totalVolumeM3", req.getTotalVolumeM3());
        m.put("fillPercentOf11t", req.getExpectedFillPercent());
        m.put("proposedFee", fee);
        m.put("baseDistanceKm", metrics.baseKm());
        m.put("viaCargoDistanceKm", metrics.viaCargoKm());
        m.put("extraDistanceKm", metrics.extraKm());
        m.put("detourRatio", metrics.detourRatio());
        m.put("extraFuelCost", extraFuelCost);
        m.put("netProfit", net);
        m.put("esgReductionKg", esg);
        m.put("remainingVolumePercent", rem);
        m.put("onRoute", metrics.onRoute());
        m.put("briefing", String.format(
                "%s → %s · 우회 +%.1fkm · 순이익 %,d원 · ESG %.1fkg",
                req.getOrigin(), req.getDestination(), metrics.extraKm(), net, esg));
        m.put("route", (req.getOrigin() != null ? req.getOrigin() : "")
                + (req.getViaStation() != null && !req.getViaStation().isBlank()
                    ? " → " + req.getViaStation().replace(",", " → ") : "")
                + " → " + (req.getDestination() != null ? req.getDestination() : ""));
        m.put("status", req.getStatus());
        m.put("createdAt", req.getCreatedAt() != null ? req.getCreatedAt().toString() : null);
        return m;
    }

    @GetMapping("/truck-status")
    public Map<String, Object> truckStatus(@RequestParam(required = false) Long truckId) {
        Truck truck = truckId != null
                ? truckRepository.findById(truckId).orElse(null)
                : truckRepository.findAll().stream().findFirst().orElse(null);
        if (truck == null) throw new NoSuchElementException("차량 없음");
        return truckToMap(truck);
    }

    /** 시연: 선택 기사(또는 전체) 잔여 100% + 정산 초기화 */
    @PostMapping("/truck/reset-empty")
    public Map<String, Object> resetEmptyTruck(@RequestParam(required = false) Long truckId) {
        List<Truck> trucks = truckRepository.findAll();
        for (Truck truck : trucks) {
            if (truckId != null && !truck.getId().equals(truckId)) continue;
            truck.setRemainingVolumePercent(100.0);
            truck.setExpectedAddedFillPercent(null);
            truck.setBaselineOccupiedPercent(null);
            truck.setActiveRequestId(null);
            truck.setStatus("IDLE");
            truckRepository.save(truck);
        }
        loadHistoryRepository.deleteAll();
        Map<String, Object> res = new LinkedHashMap<>();
        res.put("ledgerCleared", true);
        res.put("entryCount", 0);
        res.put("drivers", trucks.stream().map(this::truckToMap).toList());
        return res;
    }

    /** 운행 완료/공차: 잔여 100%·대기 (정산 이력은 유지) */
    @PostMapping("/truck/clear-space")
    public Map<String, Object> clearTruckSpace(@RequestParam Long truckId) {
        Truck truck = truckRepository.findById(truckId)
                .orElseThrow(() -> new NoSuchElementException("차량 없음: " + truckId));
        truck.setRemainingVolumePercent(100.0);
        truck.setExpectedAddedFillPercent(null);
        truck.setBaselineOccupiedPercent(null);
        truck.setActiveRequestId(null);
        truck.setStatus("IDLE");
        truckRepository.save(truck);
        Map<String, Object> res = truckToMap(truck);
        res.put("message", "운행 완료 · 공차(잔여 100%)로 초기화되었습니다.");
        res.put("occupiedVolumePercent", 0.0);
        return res;
    }

    /**
     * 시연 초기화: 양방향 데모 물량 재시드 + 전 차량 공차 + 정산 비움.
     * 관리자/화물등록 화면에서 반복 시연용.
     */
    @PostMapping("/demo-reset")
    @Transactional
    public Map<String, Object> demoReset() {
        Map<String, Object> seed = demoOdSeedService.seedBusanSeoulCorridor(true);
        int trucks = 0;
        for (Truck truck : truckRepository.findAll()) {
            truck.setRemainingVolumePercent(100.0);
            truck.setExpectedAddedFillPercent(null);
            truck.setBaselineOccupiedPercent(null);
            truck.setActiveRequestId(null);
            truck.setStatus("IDLE");
            truckRepository.save(truck);
            trucks++;
        }
        loadHistoryRepository.deleteAll();
        long epoch = DEMO_EPOCH.incrementAndGet();
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("message", "시연 데이터가 초기 상태로 복구되었습니다.");
        out.put("seed", seed);
        out.put("trucksReset", trucks);
        out.put("ledgerCleared", true);
        out.put("groupsCreated", seed.get("groupsCreated"));
        out.put("terminals", seed.get("terminals"));
        out.put("epoch", epoch);
        return out;
    }

    @GetMapping("/demo-state")
    public Map<String, Object> demoState() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("epoch", DEMO_EPOCH.get());
        return out;
    }

    private Map<String, Object> truckToMap(Truck truck) {
        double remaining = truck.getRemainingVolumePercent() != null ? truck.getRemainingVolumePercent() : 100.0;
        Map<String, Object> res = new LinkedHashMap<>();
        res.put("truckId", truck.getId());
        res.put("driverName", truck.getDriverName());
        res.put("phone", truck.getPhone());
        res.put("truckNumber", truck.getTruckNumber());
        res.put("capacityTons", truck.getCapacityTons());
        res.put("capacityM3", truck.getCapacityM3());
        res.put("vehicleType", truck.getVehicleType());
        res.put("profileCompleted", Boolean.TRUE.equals(truck.getProfileCompleted()));
        res.put("originCode", truck.getOriginCode());
        res.put("destinationCode", truck.getDestinationCode());
        res.put("originName", truck.getOriginName());
        res.put("destinationName", truck.getDestinationName());
        res.put("remainingVolumePercent", remaining);
        res.put("occupiedVolumePercent", Math.round((100.0 - remaining) * 100.0) / 100.0);
        res.put("status", truck.getStatus());
        res.put("activeRequestId", truck.getActiveRequestId());
        return res;
    }

    @GetMapping("/ledger")
    public Map<String, Object> ledger(@RequestParam(required = false) Long truckId) {
        List<LoadHistory> rows = loadHistoryRepository.findAll().stream()
                .filter(r -> r.getIncome() != null && r.getIncome() > 0)
                .filter(r -> truckId == null || (r.getTruckId() != null && r.getTruckId().equals(truckId)))
                .sorted(Comparator.comparing(LoadHistory::getCreatedAt, Comparator.nullsLast(Comparator.naturalOrder())).reversed())
                .toList();

        int income = rows.stream().mapToInt(LoadHistory::getIncome).sum();
        int expense = rows.stream().mapToInt(r -> r.getExpense() != null ? r.getExpense() : 0).sum();
        double esg = rows.stream().mapToDouble(r -> r.getEsgReductionKg() != null ? r.getEsgReductionKg() : 0).sum();
        esg = Math.round(esg * 100.0) / 100.0;

        List<Map<String, Object>> entries = rows.stream().map(r -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", r.getId());
            m.put("cargoRequestId", r.getCargoRequestId());
            m.put("truckId", r.getTruckId());
            m.put("origin", r.getOrigin());
            m.put("destination", r.getDestination());
            String route = r.getRouteSummary();
            if (route == null || route.isBlank()) {
                route = (r.getOrigin() != null ? r.getOrigin() : "?")
                        + " → " + (r.getDestination() != null ? r.getDestination() : "?");
            }
            m.put("route", route);
            m.put("income", r.getIncome());
            m.put("expense", r.getExpense() != null ? r.getExpense() : 0);
            m.put("netProfit", r.getNetProfit() != null ? r.getNetProfit() : r.getIncome());
            m.put("esgReductionKg", r.getEsgReductionKg());
            m.put("createdAt", r.getCreatedAt() != null ? r.getCreatedAt().toString() : null);

            // 건별 물량·터미널 상세 (CargoRequest 조인)
            Integer boxCount = null;
            Double volumeM3 = null;
            Double fillPercent = null;
            String originCode = null;
            String destinationCode = null;
            if (r.getCargoRequestId() != null) {
                CargoRequest cr = cargoRequestRepository.findById(r.getCargoRequestId()).orElse(null);
                if (cr != null) {
                    boxCount = cr.getBoxCount();
                    volumeM3 = cr.getTotalVolumeM3();
                    fillPercent = cr.getExpectedFillPercent();
                    originCode = cr.getOriginCode();
                    destinationCode = cr.getDestinationCode();
                    if (m.get("origin") == null || String.valueOf(m.get("origin")).isBlank()) {
                        m.put("origin", cr.getOrigin());
                    }
                    if (m.get("destination") == null || String.valueOf(m.get("destination")).isBlank()) {
                        m.put("destination", cr.getDestination());
                    }
                }
                try {
                    var og = cargoOdGroupService.findByCargoRequestId(r.getCargoRequestId());
                    if (og.isPresent()) {
                        var g = og.get();
                        if (boxCount == null) boxCount = g.getBoxCount() != null ? g.getBoxCount() : g.getWaybillCount();
                        if (volumeM3 == null) volumeM3 = g.getVolumeM3();
                        if (originCode == null) originCode = g.getOriginTerminalCode();
                        if (destinationCode == null) destinationCode = g.getDestinationTerminalCode();
                        if (fillPercent == null && g.getFillPercentOf11t() != null) {
                            fillPercent = g.getFillPercentOf11t();
                        }
                        if (g.getOriginTerminalName() != null) m.put("origin", g.getOriginTerminalName());
                        if (g.getDestinationTerminalName() != null) m.put("destination", g.getDestinationTerminalName());
                    }
                } catch (Exception ignored) { /* optional enrich */ }
            }
            m.put("boxCount", boxCount != null ? boxCount : 0);
            m.put("volumeM3", volumeM3 != null ? Math.round(volumeM3 * 100.0) / 100.0 : null);
            m.put("fillPercent", fillPercent != null ? Math.round(fillPercent * 10.0) / 10.0 : null);
            m.put("originCode", originCode);
            m.put("destinationCode", destinationCode);
            m.put("title",
                    (m.get("origin") != null ? m.get("origin") : "?")
                            + " → "
                            + (m.get("destination") != null ? m.get("destination") : "?"));
            return m;
        }).toList();

        Map<String, Object> res = new LinkedHashMap<>();
        res.put("entries", entries);
        res.put("totalIncome", income);
        res.put("totalExpense", expense);
        res.put("netProfit", income - expense);
        res.put("dailyEsgKg", esg);
        res.put("entryCount", entries.size());
        res.put("truckId", truckId);
        return res;
    }
}
