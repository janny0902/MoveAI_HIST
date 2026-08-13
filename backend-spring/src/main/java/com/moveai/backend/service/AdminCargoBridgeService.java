package com.moveai.backend.service;

import com.moveai.backend.entity.CargoOdGroup;
import com.moveai.backend.entity.CargoOdItem;
import com.moveai.backend.entity.CargoRequest;
import com.moveai.backend.repository.CargoOdGroupRepository;
import com.moveai.backend.repository.CargoOdItemRepository;
import com.moveai.backend.repository.CargoRequestRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.util.*;

/**
 * matching 체적 → OD 그룹 + 개별 아이템(그룹당 최대 500).
 * 출도착 키·GPS는 작업터미널 코드 기준(기사와 동일).
 */
@Service
public class AdminCargoBridgeService {

    private static final Logger log = LoggerFactory.getLogger(AdminCargoBridgeService.class);
    private static final String ROUTE_PREFIX = "route:";
    private static final int MAX_ITEMS_PER_GROUP = 500;

    private final CargoOdGroupRepository cargoOdGroupRepository;
    private final CargoOdItemRepository cargoOdItemRepository;
    private final CargoRequestRepository cargoRequestRepository;
    private final CalculationService calculationService;
    private final TerminalRegistryService terminalRegistry;
    private final RestTemplate adminProxyRestTemplate;

    @Value("${admin.matching.base-url:https://matching-processor-xi6ooeq3ta-du.a.run.app}")
    private String matchingBaseUrl;

    public AdminCargoBridgeService(
            CargoOdGroupRepository cargoOdGroupRepository,
            CargoOdItemRepository cargoOdItemRepository,
            CargoRequestRepository cargoRequestRepository,
            CalculationService calculationService,
            TerminalRegistryService terminalRegistry,
            @Qualifier("adminProxyRestTemplate") RestTemplate adminProxyRestTemplate
    ) {
        this.cargoOdGroupRepository = cargoOdGroupRepository;
        this.cargoOdItemRepository = cargoOdItemRepository;
        this.cargoRequestRepository = cargoRequestRepository;
        this.calculationService = calculationService;
        this.terminalRegistry = terminalRegistry;
        this.adminProxyRestTemplate = adminProxyRestTemplate;
    }

    @Transactional
    public Map<String, Object> ensureOdGroupsBuilt(String driverOriginTerminal) {
        if (cargoOdGroupRepository.count() > 0) {
            return Map.of(
                    "skipped", true,
                    "reason", "already-built",
                    "groupCount", cargoOdGroupRepository.count()
            );
        }
        return buildOdGroups(driverOriginTerminal, 500);
    }

    @Transactional
    public Map<String, Object> buildOdGroups(String driverOriginTerminal, int limitPerTerminal) {
        List<String> terminals = resolveOriginTerminals(driverOriginTerminal);
        Map<String, RouteAgg> groups = new LinkedHashMap<>();
        int fetched = 0;
        List<String> errors = new ArrayList<>();
        int perPage = Math.min(Math.max(limitPerTerminal, 100), 500);
        int maxPages = 3;

        for (String term : terminals) {
            for (int page = 1; page <= maxPages; page++) {
                try {
                    List<Map<String, Object>> cargos = fetchCargos(term, null, perPage, page);
                    if (cargos.isEmpty()) break;
                    fetched += cargos.size();
                    for (Map<String, Object> c : cargos) {
                        accumulate(groups, c);
                    }
                    if (cargos.size() < perPage) break;
                } catch (Exception e) {
                    errors.add(term + " p" + page + ": " + e.getMessage());
                    log.warn("OD build failed for {} page {}: {}", term, page, e.toString());
                    break;
                }
            }
        }
        try {
            List<Map<String, Object>> latest = fetchCargos(null, null, 500, 1);
            fetched += latest.size();
            for (Map<String, Object> c : latest) {
                accumulate(groups, c);
            }
        } catch (Exception e) {
            errors.add("latest: " + e.getMessage());
        }

        int upserted = 0;
        int itemsSaved = 0;
        LocalDateTime now = LocalDateTime.now();
        List<Map<String, Object>> preview = new ArrayList<>();

        for (RouteAgg g : groups.values()) {
            if (g.volumeM3 <= 0 || g.waybillCount <= 0) continue;
            CargoOdGroup row = upsertOdGroup(g, now);
            itemsSaved += persistItems(row, g);
            Long reqId = upsertLinkedRequest(row);
            if (reqId != null && !Objects.equals(row.getCargoRequestId(), reqId)) {
                row.setCargoRequestId(reqId);
                cargoOdGroupRepository.save(row);
            }
            upserted++;
            if (preview.size() < 15) {
                Map<String, Object> p = new LinkedHashMap<>();
                p.put("id", row.getId());
                p.put("routeKey", row.getRouteKey());
                p.put("origin", row.getOriginTerminalCode());
                p.put("destination", row.getDestinationTerminalCode());
                p.put("waybills", row.getWaybillCount());
                p.put("boxes", row.getBoxCount());
                p.put("volumeM3", row.getVolumeM3());
                p.put("fillPercent", row.getFillPercentOf11t());
                p.put("itemsStored", Math.min(g.samples.size(), MAX_ITEMS_PER_GROUP));
                p.put("cargoRequestId", row.getCargoRequestId());
                preview.add(p);
            }
        }

        int retired = 0;
        for (CargoRequest req : cargoRequestRepository.findByStatusOrderByCreatedAtDesc("PENDING")) {
            String ext = req.getExternalCargoId();
            if (ext != null && !ext.startsWith(ROUTE_PREFIX)) {
                req.setStatus("UNMATCHED");
                cargoRequestRepository.save(req);
                retired++;
            }
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("mode", "cargo_od_groups");
        out.put("fetched", fetched);
        out.put("routeGroups", groups.size());
        out.put("upserted", upserted);
        out.put("itemsSaved", itemsSaved);
        out.put("retiredSingles", retired);
        out.put("tableCount", cargoOdGroupRepository.count());
        out.put("originTerminals", terminals);
        out.put("errors", errors);
        out.put("preview", preview);
        return out;
    }

    public List<CargoOdGroup> listOdGroups() {
        return cargoOdGroupRepository.findAllByOrderByVolumeM3Desc();
    }

    private List<String> resolveOriginTerminals(String driverOrigin) {
        LinkedHashSet<String> set = new LinkedHashSet<>();
        if (driverOrigin != null && !driverOrigin.isBlank()) {
            String code = driverOrigin.trim();
            // 숫자형 터미널 코드
            if (code.matches("\\d+")) {
                set.add(code);
                // 같은 권역 인접 (앞자리)
                String prefix = code.length() >= 1 ? code.substring(0, 1) : code;
                for (TerminalRegistryService.Terminal t : terminalRegistry.listTerminals()) {
                    if (t.code().startsWith(prefix) && set.size() < 8) {
                        set.add(t.code());
                    }
                }
            } else {
                // 구 KTX 코드 호환
                Map<String, List<String>> legacy = Map.of(
                        "BUSAN", List.of("200", "201", "202", "203"),
                        "SEOUL", List.of("001", "002", "003", "008"),
                        "DONGDAEGU", List.of("300", "301", "302"),
                        "DAEJEON", List.of("500", "501"),
                        "GWANGJU", List.of("400", "401")
                );
                set.addAll(legacy.getOrDefault(code.toUpperCase(Locale.ROOT), List.of()));
            }
        }
        if (set.isEmpty()) {
            set.addAll(List.of("200", "201", "202", "001", "008"));
        }
        return new ArrayList<>(set);
    }

    private CargoOdGroup upsertOdGroup(RouteAgg g, LocalDateTime now) {
        String routeKey = g.originCode + ":" + g.destCode;
        var oTerm = terminalRegistry.findByCode(g.originCode).orElse(null);
        var dTerm = terminalRegistry.findByCode(g.destCode).orElse(null);

        double oLat = g.pickupLat != 0 ? g.pickupLat : (oTerm != null ? oTerm.lat() : 0);
        double oLng = g.pickupLng != 0 ? g.pickupLng : (oTerm != null ? oTerm.lng() : 0);
        double dLat = g.dropLat != 0 ? g.dropLat : (dTerm != null ? dTerm.lat() : 0);
        double dLng = g.dropLng != 0 ? g.dropLng : (dTerm != null ? dTerm.lng() : 0);

        String originName = firstNonBlank(g.originName, oTerm != null ? oTerm.name() : null, g.originCode);
        String destName = firstNonBlank(g.destName, dTerm != null ? dTerm.name() : null, g.destCode);
        double volumeM3 = round4(g.volumeM3);
        double weight = g.weightKg > 0 ? g.weightKg : g.boxCount * 8.0;
        // 0원도 유효. 음수/미설정(-1 등)일 때만 박스 기본 단가
        int fee = g.freightKrw >= 0 ? g.freightKrw : g.boxCount * 1500;
        double fill = calculationService.calculateFillPercentOf11t(volumeM3);

        CargoOdGroup row = cargoOdGroupRepository.findByRouteKey(routeKey).orElseGet(CargoOdGroup::new);
        row.setRouteKey(routeKey);
        row.setOriginTerminalCode(g.originCode);
        row.setOriginTerminalName(originName);
        row.setDestinationTerminalCode(g.destCode);
        row.setDestinationTerminalName(destName);
        // 터미널 코드를 경로 매칭 키로 사용 (기사 originCode와 동일 체계)
        row.setOriginStationCode(g.originCode);
        row.setDestinationStationCode(g.destCode);
        row.setOriginLat(oLat != 0 ? oLat : null);
        row.setOriginLng(oLng != 0 ? oLng : null);
        row.setDestinationLat(dLat != 0 ? dLat : null);
        row.setDestinationLng(dLng != 0 ? dLng : null);
        row.setWaybillCount(g.waybillCount);
        row.setBoxCount(g.boxCount);
        row.setVolumeM3(volumeM3);
        row.setWeightKg(weight);
        row.setFreightKrw(fee);
        row.setFillPercentOf11t(fill);
        row.setFillByVehicleJson(calculationService.toFillByVehicleJson(volumeM3));
        row.setUpdatedAt(now);
        return cargoOdGroupRepository.save(row);
    }

    private int persistItems(CargoOdGroup row, RouteAgg g) {
        int saved = 0;
        for (SampleCargo s : g.samples) {
            if (cargoOdItemRepository.countByOdGroupId(row.getId()) >= MAX_ITEMS_PER_GROUP) break;
            if (s.externalId == null || s.externalId.isBlank()) continue;
            if (cargoOdItemRepository.findByExternalCargoId(s.externalId).isPresent()) continue;
            cargoOdItemRepository.save(CargoOdItem.builder()
                    .odGroupId(row.getId())
                    .externalCargoId(s.externalId)
                    .originTerminalCode(g.originCode)
                    .destinationTerminalCode(g.destCode)
                    .boxCount(s.boxCount)
                    .volumeM3(s.volumeM3)
                    .weightKg(s.weightKg)
                    .freightKrw(s.freightKrw)
                    .productCode(s.productCode)
                    .productName(s.productName)
                    .status("WAITING")
                    .createdAt(LocalDateTime.now())
                    .build());
            saved++;
        }
        return saved;
    }

    private Long upsertLinkedRequest(CargoOdGroup g) {
        String ext = ROUTE_PREFIX + g.getRouteKey();
        Optional<CargoRequest> existing = cargoRequestRepository.findByExternalCargoId(ext);
        CargoRequest req = existing.orElseGet(CargoRequest::new);
        if (existing.isPresent()
                && !"PENDING".equals(req.getStatus())
                && !"UNMATCHED".equals(req.getStatus())) {
            return req.getId();
        }
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
        if (req.getCreatedAt() == null) {
            req.setCreatedAt(LocalDateTime.now());
        }
        return cargoRequestRepository.save(req).getId();
    }

    private void accumulate(Map<String, RouteAgg> groups, Map<String, Object> c) {
        String o = str(c.get("origin_terminal_code"));
        String d = str(c.get("destination_terminal_code"));
        if (o.isBlank() || d.isBlank()) return;
        double vol = num(c.get("volume_cbm"), 0);
        if (vol <= 0) return;
        String key = o + "|" + d;
        RouteAgg g = groups.computeIfAbsent(key, k -> new RouteAgg(o, d));
        g.waybillCount += 1;
        int boxes = (int) Math.max(1, Math.round(num(c.get("box_count"), 1)));
        g.boxCount += boxes;
        g.volumeM3 += vol;
        g.weightKg += num(c.get("weight_kg"), 0);
        g.freightKrw += (int) Math.round(num(c.get("freight_krw"), 0));
        if (g.originName.isBlank()) g.originName = str(c.get("origin_terminal_name"));
        if (g.destName.isBlank()) g.destName = str(c.get("destination_terminal_name"));
        if (g.pickupLat == 0) g.pickupLat = num(c.get("pickup_lat"), 0);
        if (g.pickupLng == 0) g.pickupLng = num(c.get("pickup_lng"), 0);
        if (g.dropLat == 0) g.dropLat = num(c.get("delivery_lat"), 0);
        if (g.dropLng == 0) g.dropLng = num(c.get("delivery_lng"), 0);

        if (g.samples.size() < MAX_ITEMS_PER_GROUP) {
            String ext = firstNonBlank(str(c.get("cargo_id")), str(c.get("waybill_no")), str(c.get("id")));
            if (!ext.isBlank()) {
                g.samples.add(new SampleCargo(
                        ext,
                        boxes,
                        vol,
                        num(c.get("weight_kg"), boxes * 8.0),
                        (int) Math.round(num(c.get("freight_krw"), boxes * 1500.0)),
                        firstNonBlank(str(c.get("product_code")), "Box"),
                        firstNonBlank(str(c.get("product_name")), "박스")
                ));
            }
        }
    }

    private List<Map<String, Object>> fetchCargos(String originTerminal, String destTerminal, int limit, int page) {
        StringBuilder url = new StringBuilder(matchingBaseUrl.replaceAll("/$", ""))
                .append("/v1/cargos?limit=").append(limit).append("&page=").append(Math.max(1, page));
        if (originTerminal != null && !originTerminal.isBlank()) {
            url.append("&terminal_code=").append(originTerminal);
        }
        if (destTerminal != null && !destTerminal.isBlank()) {
            url.append("&destination_terminal_code=").append(destTerminal);
        }
        ResponseEntity<Map<String, Object>> res = adminProxyRestTemplate.exchange(
                url.toString(), HttpMethod.GET, null,
                new ParameterizedTypeReference<>() {}
        );
        Object raw = res.getBody() != null ? res.getBody().get("cargos") : null;
        if (!(raw instanceof List<?> list)) return List.of();
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object o : list) {
            if (o instanceof Map<?, ?> m) {
                @SuppressWarnings("unchecked")
                Map<String, Object> cast = (Map<String, Object>) m;
                out.add(cast);
            }
        }
        return out;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o).trim();
    }

    private static double num(Object o, double def) {
        if (o == null) return def;
        if (o instanceof Number n) return n.doubleValue();
        try {
            return Double.parseDouble(String.valueOf(o));
        } catch (Exception e) {
            return def;
        }
    }

    private static double round4(double v) {
        return Math.round(v * 10000.0) / 10000.0;
    }

    private static String firstNonBlank(String... vals) {
        for (String v : vals) {
            if (v != null && !v.isBlank()) return v;
        }
        return "";
    }

    private static final class RouteAgg {
        final String originCode;
        final String destCode;
        String originName = "";
        String destName = "";
        int waybillCount;
        int boxCount;
        double volumeM3;
        double weightKg;
        int freightKrw;
        double pickupLat;
        double pickupLng;
        double dropLat;
        double dropLng;
        final List<SampleCargo> samples = new ArrayList<>();

        RouteAgg(String originCode, String destCode) {
            this.originCode = originCode;
            this.destCode = destCode;
        }
    }

    private record SampleCargo(
            String externalId,
            int boxCount,
            double volumeM3,
            double weightKg,
            int freightKrw,
            String productCode,
            String productName
    ) {}
}
