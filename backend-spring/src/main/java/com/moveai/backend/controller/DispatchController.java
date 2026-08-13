package com.moveai.backend.controller;

import com.moveai.backend.entity.LoadHistory;
import com.moveai.backend.entity.Truck;
import com.moveai.backend.repository.LoadHistoryRepository;
import com.moveai.backend.repository.TruckRepository;
import com.moveai.backend.service.StationCatalog;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/**
 * Bootstrap dispatch stubs — full matching/nearby/navi lands in later phases.
 */
@RestController
@RequestMapping("/api/dispatch")
public class DispatchController {
    private final StationCatalog stations;
    private final TruckRepository truckRepository;
    private final LoadHistoryRepository loadHistoryRepository;
    private final AtomicLong demoEpoch = new AtomicLong(1);

    public DispatchController(
            StationCatalog stations,
            TruckRepository truckRepository,
            LoadHistoryRepository loadHistoryRepository) {
        this.stations = stations;
        this.truckRepository = truckRepository;
        this.loadHistoryRepository = loadHistoryRepository;
    }

    @GetMapping("/stations")
    public Map<String, Object> stations() {
        return Map.of("stations", stations.all());
    }

    @GetMapping("/terminals")
    public Map<String, Object> terminals() {
        return Map.of("terminals", stations.all());
    }

    @GetMapping("/cargo-feed")
    public Map<String, Object> cargoFeed(@RequestParam(required = false) Long truckId) {
        double rem = 100;
        if (truckId != null) {
            rem = truckRepository.findById(truckId)
                    .map(t -> t.getRemainingVolumePercent() == null ? 100.0 : t.getRemainingVolumePercent())
                    .orElse(100.0);
        }
        Map<String, Object> res = new HashMap<>();
        res.put("items", List.of());
        res.put("notifications", List.of());
        res.put("remainingVolumePercent", rem);
        res.put("count", 0);
        return res;
    }

    @GetMapping("/offers")
    public Map<String, Object> offers(@RequestParam(required = false) Long truckId) {
        Map<String, Object> feed = cargoFeed(truckId);
        Map<String, Object> res = new HashMap<>(feed);
        res.put("offers", feed.get("items"));
        return res;
    }

    @GetMapping("/nearby-loadable")
    public Map<String, Object> nearby(
            @RequestParam Long truckId,
            @RequestParam double lat,
            @RequestParam double lng,
            @RequestParam(defaultValue = "20") double radiusKm,
            @RequestParam(required = false) Double remainingPercent,
            @RequestParam(required = false) String destinationCode) {
        Map<String, Object> res = new HashMap<>();
        res.put("items", List.of());
        res.put("count", 0);
        res.put("radiusKm", radiusKm);
        res.put("truckId", truckId);
        res.put("lat", lat);
        res.put("lng", lng);
        res.put("remainingPercent", remainingPercent);
        res.put("destinationCode", destinationCode);
        res.put("destinationRegion", regionOf(destinationCode));
        res.put("message", "bootstrap: nearby matching not wired yet");
        return res;
    }

    @GetMapping("/ledger")
    public Map<String, Object> ledger(@RequestParam Long truckId) {
        List<LoadHistory> rows = loadHistoryRepository.findByTruckIdOrderByCreatedAtDesc(truckId);
        List<Map<String, Object>> entries = rows.stream()
                .filter(h -> h.getIncome() != null && h.getIncome() > 0)
                .map(h -> {
                    Map<String, Object> e = new HashMap<>();
                    e.put("id", h.getId());
                    e.put("route", h.getRouteSummary() == null ? "" : h.getRouteSummary());
                    e.put("income", h.getIncome());
                    e.put("expense", h.getExpense());
                    e.put("netProfit", h.getNetProfit());
                    e.put("esgReductionKg", h.getEsgReductionKg());
                    return e;
                })
                .toList();
        int income = entries.stream().mapToInt(e -> (Integer) e.get("income")).sum();
        int expense = entries.stream().mapToInt(e -> (Integer) e.get("expense")).sum();
        double esg = entries.stream().mapToDouble(e -> ((Number) e.get("esgReductionKg")).doubleValue()).sum();
        Map<String, Object> res = new HashMap<>();
        res.put("entries", entries);
        res.put("totalIncome", income);
        res.put("totalExpense", expense);
        res.put("netProfit", income - expense);
        res.put("dailyEsgKg", esg);
        res.put("entryCount", entries.size());
        return res;
    }

    @GetMapping("/demo-state")
    public Map<String, Object> demoState() {
        return Map.of("epoch", demoEpoch.get());
    }

    @PostMapping("/demo-reset")
    @Transactional
    public Map<String, Object> demoReset() {
        for (Truck t : truckRepository.findAll()) {
            t.setRemainingVolumePercent(100.0);
            t.setStatus("IDLE");
            t.setActiveRequestId(null);
            truckRepository.save(t);
            loadHistoryRepository.deleteByTruckId(t.getId());
        }
        return Map.of("epoch", demoEpoch.incrementAndGet());
    }

    @PostMapping("/truck/reset-empty")
    @Transactional
    public Map<String, Object> resetEmpty(@RequestParam Long truckId) {
        Truck t = truckRepository.findById(truckId).orElse(null);
        if (t != null) {
            t.setRemainingVolumePercent(100.0);
            truckRepository.save(t);
            loadHistoryRepository.deleteByTruckId(truckId);
        }
        return Map.of("status", "OK", "truckId", truckId, "remainingVolumePercent", 100);
    }

    private static String regionOf(String code) {
        if (code == null) return null;
        if (code.equals("001") || code.equals("008") || code.equals("SEOUL")) return "SEOUL";
        if (code.equals("200") || code.equals("201") || code.equals("BUSAN")) return "BUSAN";
        return code;
    }
}
