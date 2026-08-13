package com.moveai.backend.service;

import com.moveai.backend.entity.LoadHistory;
import com.moveai.backend.entity.Truck;
import com.moveai.backend.repository.LoadHistoryRepository;
import com.moveai.backend.repository.TruckRepository;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class LoadService {
    private final TruckRepository truckRepository;
    private final LoadHistoryRepository loadHistoryRepository;
    private final AiClient aiClient;

    public LoadService(TruckRepository truckRepository, LoadHistoryRepository loadHistoryRepository, AiClient aiClient) {
        this.truckRepository = truckRepository;
        this.loadHistoryRepository = loadHistoryRepository;
        this.aiClient = aiClient;
    }

    @Transactional
    public Map<String, Object> upload(MultipartFile file, Long truckId) {
        Truck truck = truckRepository.findById(truckId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "truck not found"));
        try {
            Map<String, Object> ai = aiClient.analyzeImage(file.getBytes(), file.getOriginalFilename());
            double remaining = toDouble(ai.get("remaining_volume_percent"), 100);
            double occupied = toDouble(ai.get("occupied_volume_percent"), Math.max(0, 100 - remaining));
            truck.setRemainingVolumePercent(remaining);
            truck.setStatus("LOADING");
            truckRepository.save(truck);

            LoadHistory history = new LoadHistory();
            history.setTruckId(truckId);
            history.setLoadImageUrl(file.getOriginalFilename());
            history.setRemainingVolumePercent(remaining);
            history.setOccupiedVolumePercent(occupied);
            history = loadHistoryRepository.save(history);

            Map<String, Object> res = new HashMap<>();
            res.put("historyId", history.getId());
            res.put("remainingVolumePercent", remaining);
            res.put("occupiedVolumePercent", occupied);
            res.put("status", ai.getOrDefault("status", "ok"));
            res.put("verifyStatus", "NO_EXPECTED");
            res.put("expectedAddedFillPercent", truck.getExpectedAddedFillPercent());
            res.put("baselineOccupiedPercent", truck.getBaselineOccupiedPercent());
            res.put("guide", ai.getOrDefault("guide", ""));
            res.put("engine", ai.getOrDefault("engine", ""));
            res.put("pipeline", ai.getOrDefault("pipeline", List.of()));
            res.put("logs", ai.getOrDefault("logs", List.of()));
            return res;
        } catch (ResponseStatusException e) {
            throw e;
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "AI analyze failed: " + e.getMessage());
        }
    }

    private static double toDouble(Object v, double fallback) {
        if (v == null) return fallback;
        if (v instanceof Number n) return n.doubleValue();
        try {
            return Double.parseDouble(String.valueOf(v));
        } catch (Exception e) {
            return fallback;
        }
    }
}
