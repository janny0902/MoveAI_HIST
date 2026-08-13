package com.moveai.backend.service;

import com.moveai.backend.entity.CargoOdGroup;
import com.moveai.backend.entity.CargoRequest;
import com.moveai.backend.entity.Truck;
import com.moveai.backend.repository.CargoRequestRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 기사 출도착 기준 후보 점수화 + LLM 순위 → 최적 배차 플랜.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class OptimalDispatchService {

    private final OdDetourService odDetourService;
    private final AdminCargoBridgeService adminCargoBridgeService;
    private final CargoRequestRepository cargoRequestRepository;
    private final CalculationService calculationService;
    private final DispatchCartService dispatchCartService;
    private final RestTemplate restTemplate;

    @Value("${ai.base-url:http://backend-ai:8000}")
    private String aiBaseUrl;

    public Map<String, Object> buildPlan(Truck truck) {
        long t0 = System.currentTimeMillis();
        double rem = truck.getRemainingVolumePercent() != null ? truck.getRemainingVolumePercent() : 100.0;
        List<CargoOdGroup> pending = pendingGroups();
        // 행렬 기반 증분(캐시 miss만 카카오) — 후보 10건이면 조기 종료 (카카오 leg 호출 폭주 방지)
        OdDetourService.PageResult scored = odDetourService.pageForTruck(truck, pending, 0, rem, null, true);
        List<OdDetourService.Candidate> pool = new ArrayList<>(scored.pageItems());
        for (int p = 1; p < 2 && scored.hasMore() && pool.size() < 10; p++) {
            OdDetourService.PageResult more = odDetourService.pageForTruck(truck, pending, p, rem, null, true);
            pool.addAll(more.pageItems());
            scored = more;
            if (!more.hasMore()) break;
        }
        long detourMs = System.currentTimeMillis() - t0;

        List<Map<String, Object>> candidates = new ArrayList<>();
        for (OdDetourService.Candidate c : pool) {
            CargoOdGroup g = c.group();
            if (g.getCargoRequestId() == null) continue;
            double extra = c.roadExtraKm() != null ? c.roadExtraKm() : c.straightExtraKm();
            int fee = g.getFreightKrw() != null ? g.getFreightKrw() : 0;
            int fuel = calculationService.calculateExtraFuelCost(extra);
            int net = fee - fuel;
            double extraMin = c.extraMinutes() != null ? c.extraMinutes() : Math.round(extra / 60.0 * 60);
            double fill = c.fillPercent() > 0 ? c.fillPercent()
                    : calculationService.resolveFillForTruck(g.getVolumeM3(), g.getFillByVehicleJson(), truck);
            // 점수: 수익↑ 거리·시간↓
            double score = net / (1.0 + extra) / (1.0 + extraMin / 10.0);
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("requestId", g.getCargoRequestId());
            m.put("odGroupId", g.getId());
            m.put("routeKey", g.getRouteKey());
            m.put("origin", g.getOriginTerminalName());
            m.put("destination", g.getDestinationTerminalName());
            m.put("originCode", g.getOriginTerminalCode());
            m.put("destinationCode", g.getDestinationTerminalCode());
            m.put("waybillCount", g.getWaybillCount());
            m.put("boxCount", g.getBoxCount());
            m.put("proposedFee", fee);
            m.put("extraDistanceKm", extra);
            m.put("extraMinutes", extraMin);
            m.put("extraFuelCost", fuel);
            m.put("netProfit", net);
            m.put("pickupDistanceKm", c.pickupDistKm());
            m.put("fillPercentOf11t", g.getFillPercentOf11t());
            m.put("fillPercent", fill);
            m.put("fillByVehicle", calculationService.parseFillByVehicleJson(g.getFillByVehicleJson()));
            m.put("heuristicScore", Math.round(score * 100.0) / 100.0);
            candidates.add(m);
        }
        candidates.sort(Comparator.comparingDouble(a -> -((Number) a.get("heuristicScore")).doubleValue()));

        long tLlm = System.currentTimeMillis();
        Map<String, Object> llm = callLlm(truck, candidates);
        long llmMs = System.currentTimeMillis() - tLlm;
        @SuppressWarnings("unchecked")
        List<Number> rankedIds = llm.get("rankedRequestIds") instanceof List<?>
                ? (List<Number>) llm.get("rankedRequestIds")
                : List.of();

        List<Map<String, Object>> recommended = new ArrayList<>();
        Set<Long> used = new HashSet<>();
        double fillBudget = rem;
        for (Number idNum : rankedIds) {
            Long id = idNum.longValue();
            Map<String, Object> hit = candidates.stream()
                    .filter(c -> Objects.equals(((Number) c.get("requestId")).longValue(), id))
                    .findFirst().orElse(null);
            if (hit == null || used.contains(id)) continue;
            double fill = hit.get("fillPercent") instanceof Number n ? n.doubleValue()
                    : (hit.get("fillPercentOf11t") instanceof Number n2 ? n2.doubleValue() : 0);
            if (fill > fillBudget + 0.01) continue;
            recommended.add(hit);
            used.add(id);
            fillBudget -= fill;
            if (recommended.size() >= 5) break;
        }
        // LLM이 비면 휴리스틱 top
        if (recommended.isEmpty()) {
            for (Map<String, Object> c : candidates) {
                double fill = c.get("fillPercent") instanceof Number n ? n.doubleValue()
                        : (c.get("fillPercentOf11t") instanceof Number n2 ? n2.doubleValue() : 0);
                if (fill > rem + 0.01) continue;
                recommended.add(c);
                rem -= fill;
                if (recommended.size() >= 5) break;
            }
        }

        // 선택 후 상차 순서를 기사 진행 방향(복화 축)에 맞게 재정렬 — 부산→대구→부산 역행 방지
        recommended = sortByPickupAlongDriver(truck, recommended);

        int totalNet = recommended.stream().mapToInt(c -> ((Number) c.get("netProfit")).intValue()).sum();
        double totalExtra = recommended.stream().mapToDouble(c -> ((Number) c.get("extraDistanceKm")).doubleValue()).sum();
        double totalMin = recommended.stream().mapToDouble(c -> ((Number) c.get("extraMinutes")).doubleValue()).sum();

        List<String> routeHints = new ArrayList<>();
        routeHints.add(nz(truck.getOriginName(), truck.getOriginCode()));
        for (Map<String, Object> r : recommended) {
            routeHints.add(String.valueOf(r.get("origin")) + "(상차)");
            routeHints.add(String.valueOf(r.get("destination")) + "(하차)");
        }
        routeHints.add(nz(truck.getDestinationName(), truck.getDestinationCode()));

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("truckId", truck.getId());
        out.put("driverOrigin", truck.getOriginName());
        out.put("driverDestination", truck.getDestinationName());
        out.put("mode", "llm");
        out.put("candidatesConsidered", candidates.size());
        out.put("recommended", recommended);
        out.put("requestIds", recommended.stream().map(r -> r.get("requestId")).toList());
        out.put("summary", Map.of(
                "count", recommended.size(),
                "totalNetProfit", totalNet,
                "totalExtraKm", Math.round(totalExtra * 10.0) / 10.0,
                "totalExtraMinutes", Math.round(totalMin),
                "routeHint", String.join(" → ", routeHints)
        ));
        out.put("briefing", llm.getOrDefault("briefing", "수익·거리·시간을 균형 잡은 복화 조합입니다."));
        out.put("llmSource", llm.getOrDefault("source", "heuristic"));
        if (llm.get("llmError") != null) out.put("llmError", llm.get("llmError"));
        out.put("timingMs", Map.of(
                "detour", detourMs,
                "llm", llmMs,
                "total", System.currentTimeMillis() - t0
        ));
        log.info("optimal-plan truck={} candidates={} source={} detourMs={} llmMs={} totalMs={}",
                truck.getId(), candidates.size(), out.get("llmSource"), detourMs, llmMs,
                System.currentTimeMillis() - t0);
        return out;
    }

    private List<Map<String, Object>> sortByPickupAlongDriver(Truck truck, List<Map<String, Object>> items) {
        if (items == null || items.size() <= 1) return items;
        String origin = truck.getOriginCode() != null ? truck.getOriginCode() : "200";
        String dest = truck.getDestinationCode() != null ? truck.getDestinationCode() : "001";
        List<Map<String, Object>> sorted = new ArrayList<>(items);
        sorted.sort((a, b) -> dispatchCartService.compareAlongDriver(
                String.valueOf(a.getOrDefault("originCode", "")),
                String.valueOf(b.getOrDefault("originCode", "")),
                origin, dest));
        return sorted;
    }

    private List<CargoOdGroup> pendingGroups() {
        List<CargoOdGroup> out = new ArrayList<>();
        for (CargoOdGroup g : adminCargoBridgeService.listOdGroups()) {
            if (g.getCargoRequestId() == null) continue;
            CargoRequest req = cargoRequestRepository.findById(g.getCargoRequestId()).orElse(null);
            if (req != null && "PENDING".equals(req.getStatus())) out.add(g);
        }
        return out;
    }

    private Map<String, Object> callLlm(Truck truck, List<Map<String, Object>> candidates) {
        Map<String, Object> fallback = new LinkedHashMap<>();
        fallback.put("source", "heuristic");
        fallback.put("rankedRequestIds", candidates.stream()
                .limit(8)
                .map(c -> c.get("requestId"))
                .collect(Collectors.toList()));
        fallback.put("briefing", String.format(
                "%s → %s 기준으로 순이익이 높고 우회·추가시간이 적은 복화를 골랐습니다. 일괄 수락하시겠습니까?",
                nz(truck.getOriginName(), "?"), nz(truck.getDestinationName(), "?")
        ));
        if (candidates.isEmpty()) return fallback;
        try {
            String url = aiBaseUrl.replaceAll("/$", "") + "/ai/optimal-dispatch";
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("driver_origin", truck.getOriginName());
            body.put("driver_destination", truck.getDestinationName());
            body.put("remaining_percent", truck.getRemainingVolumePercent());
            body.put("candidates", candidates.stream().limit(12).toList());
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            ResponseEntity<Map<String, Object>> res = restTemplate.exchange(
                    url, HttpMethod.POST, new HttpEntity<>(body, headers),
                    new ParameterizedTypeReference<>() {}
            );
            Map<String, Object> data = res.getBody();
            if (data == null) return fallback;
            if (data.get("rankedRequestIds") == null && data.get("ranked_request_ids") != null) {
                data.put("rankedRequestIds", data.get("ranked_request_ids"));
            }
            if (data.get("rankedRequestIds") == null) {
                data.put("rankedRequestIds", fallback.get("rankedRequestIds"));
            }
            if (Boolean.TRUE.equals(data.get("quotaLimited"))) {
                data.put("source", "fallback-quota");
            } else {
                data.putIfAbsent("source", "gemini");
            }
            if (data.get("error") != null) data.put("llmError", data.get("error"));
            return data;
        } catch (Exception e) {
            log.warn("optimal LLM failed: {}", e.toString());
            String msg = e.getMessage() != null ? e.getMessage() : e.toString();
            boolean quota = msg.contains("429") || msg.toLowerCase().contains("resource exhausted")
                    || msg.toLowerCase().contains("quota");
            fallback.put("llmError", msg);
            fallback.put("source", quota ? "fallback-quota" : "fallback");
            return fallback;
        }
    }

    private static String nz(String v, String d) {
        return v == null || v.isBlank() ? d : v;
    }
}
