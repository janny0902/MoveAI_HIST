package com.moveai.backend.controller;

import com.moveai.backend.entity.LoadHistory;
import com.moveai.backend.entity.Truck;
import com.moveai.backend.repository.LoadHistoryRepository;
import com.moveai.backend.repository.TruckRepository;
import com.moveai.backend.service.CargoPhotoStorageService;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.*;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;
import java.util.*;

@RestController
@RequestMapping("/api/load")
@RequiredArgsConstructor
public class LoadController {

    private final TruckRepository truckRepository;
    private final LoadHistoryRepository loadHistoryRepository;
    private final RestTemplate restTemplate;
    private final CargoPhotoStorageService cargoPhotoStorage;

    /**
     * 상차 이미지 업로드 → AI 분석 → DB 저장
     * 약속 적재율(예: 30%) 대비 실측이 크게 넘치면 과적재 경고
     */
    @PostMapping("/upload")
    public Map<String, Object> upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "truckId", defaultValue = "1") Long truckId
    ) throws Exception {
        List<String> logs = new ArrayList<>();
        logs.add("[1] 상차 이미지 수신: " + file.getOriginalFilename());

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        ByteArrayResource resource = new ByteArrayResource(file.getBytes()) {
            @Override
            public String getFilename() {
                return file.getOriginalFilename();
            }
        };
        body.add("file", resource);

        logs.add("[2] RFP 3단 공간실측 요청 (Depth Anything → YOLO-Seg → 3D Packing)");
        ResponseEntity<Map> aiRes = restTemplate.exchange(
                "http://backend-ai:8000/ai/analyze-image",
                HttpMethod.POST,
                new HttpEntity<>(body, headers),
                Map.class
        );

        Map analysis = aiRes.getBody();
        if (analysis != null && analysis.get("logs") instanceof List<?> aiLogs) {
            for (Object line : aiLogs) {
                logs.add(String.valueOf(line));
            }
        }
        logs.add("[3] 분석 완료: 잔여 "
                + (analysis != null ? analysis.get("remaining_volume_percent") : "?") + "% / "
                + (analysis != null ? analysis.get("status") : "?")
                + " / engine=" + (analysis != null ? analysis.get("engine") : "?"));

        Double remaining = analysis != null && analysis.get("remaining_volume_percent") != null
                ? ((Number) analysis.get("remaining_volume_percent")).doubleValue() : null;
        Double occupied = analysis != null && analysis.get("occupied_volume_percent") != null
                ? ((Number) analysis.get("occupied_volume_percent")).doubleValue() : null;
        // 분석 실패/필드 누락 시 만차(100%)로 두지 않음 — 빈 차로 안전하게
        if (remaining == null && occupied == null) {
            remaining = 100.0;
            occupied = 0.0;
            logs.add("[3-warn] AI 적재율 필드 없음 → 잔여 100% / 적재 0% (만차 기본값 금지)");
        } else if (remaining == null) {
            remaining = Math.max(0.0, 100.0 - occupied);
        } else if (occupied == null) {
            occupied = Math.max(0.0, 100.0 - remaining);
        }

        Truck truck = truckRepository.findById(truckId).orElse(null);
        Double expectedAdded = truck != null ? truck.getExpectedAddedFillPercent() : null;
        Double baselineOccupied = truck != null ? truck.getBaselineOccupiedPercent() : null;

        String guide;
        String verifyStatus;
        if (expectedAdded != null && baselineOccupied != null) {
            double expectedOccupied = baselineOccupied + expectedAdded;
            double overloadThreshold = expectedOccupied + 10.0; // 약속+10%p 초과 시 과적재 의심
            logs.add("[3-1] 약속 적재 +" + expectedAdded + "%p (기준 점유 "
                    + baselineOccupied + "% → 기대 점유 " + Math.round(expectedOccupied * 10) / 10.0 + "%)");
            logs.add("[3-2] 실측 점유 " + occupied + "% / 과적재 임계 "
                    + Math.round(overloadThreshold * 10) / 10.0 + "%");

            if (occupied > overloadThreshold) {
                guide = "과적재가 의심됩니다. 재확인하세요.";
                verifyStatus = "OVERLOAD_SUSPECTED";
                logs.add("[3-3] 약속 물량 대비 실측 과다 → 과적재 경고");
            } else if (occupied < expectedOccupied - 15.0) {
                guide = "약속 물량보다 적게 실린 것으로 보입니다. 상차 물량을 확인하세요.";
                verifyStatus = "UNDERLOAD_SUSPECTED";
            } else {
                guide = "정확한 부피가 적재되었습니다. 안전운행하세요.";
                verifyStatus = "MATCHED";
            }
        } else {
            // 약속 정보 없을 때: AI guide 또는 일반 안내
            guide = analysis != null && analysis.get("guide") != null
                    ? analysis.get("guide").toString()
                    : "정확한 부피가 적재되었습니다. 안전운행하세요.";
            verifyStatus = "NO_EXPECTED";
        }

        if (truck != null) {
            truck.setRemainingVolumePercent(remaining);
            truck.setStatus("LOADING");
            // 검증 후 약속값 클리어
            truck.setExpectedAddedFillPercent(null);
            truck.setBaselineOccupiedPercent(null);
            truck.setActiveRequestId(null);
            truckRepository.save(truck);
            logs.add("[4] 차량 잔여면적 DB 갱신");
        }

        LoadHistory history = loadHistoryRepository.save(LoadHistory.builder()
                .truckId(truckId)
                .loadImageUrl(file.getOriginalFilename())
                .remainingVolumePercent(remaining)
                .occupiedVolumePercent(occupied)
                .esgReductionKg(0.0)
                .createdAt(LocalDateTime.now())
                .build());
        logs.add("[5] 적재 이력 저장 (id=" + history.getId() + ")");

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("historyId", history.getId());
        result.put("remainingVolumePercent", remaining);
        result.put("occupiedVolumePercent", occupied);
        result.put("status", analysis != null ? analysis.get("status") : "unknown");
        result.put("verifyStatus", verifyStatus);
        result.put("expectedAddedFillPercent", expectedAdded);
        result.put("baselineOccupiedPercent", baselineOccupied);
        result.put("guide", guide);
        result.put("engine", analysis != null ? analysis.get("engine") : null);
        result.put("pipeline", analysis != null ? analysis.get("pipeline") : null);
        Object occupancyGrid = analysis != null ? analysis.get("occupancy_grid") : null;
        if (occupancyGrid == null && analysis != null) {
            occupancyGrid = analysis.get("occupancyGrid");
        }
        result.put("occupancyGrid", occupancyGrid);
        if (occupancyGrid instanceof Map<?, ?> og) {
            Object cells = og.get("cells");
            int n = cells instanceof List<?> list ? list.size() : -1;
            logs.add("[5-1] occupancyGrid 전달 cells=" + n);
        } else {
            logs.add("[5-1] occupancyGrid 없음 (프론트 격자 채움 불가)");
        }
        result.put("logs", logs);
        return result;
    }

    /**
     * 바닥 적재 더미 사진 → 가로·세로·높이(mm) · 체적 · 차종별 점유율.
     * 파일을 저장해 photoUrl도 반환 (기사 적재물보기용).
     */
    @PostMapping("/analyze-floor")
    public Map<String, Object> analyzeFloor(@RequestParam("file") MultipartFile file) throws Exception {
        String photoUrl = cargoPhotoStorage.store(file);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        ByteArrayResource resource = new ByteArrayResource(file.getBytes()) {
            @Override
            public String getFilename() {
                return file.getOriginalFilename();
            }
        };
        body.add("file", resource);
        ResponseEntity<Map> aiRes = restTemplate.exchange(
                "http://backend-ai:8000/ai/analyze-floor-cargo",
                HttpMethod.POST,
                new HttpEntity<>(body, headers),
                Map.class
        );
        Map analysis = aiRes.getBody() != null ? aiRes.getBody() : Map.of();
        Map<String, Object> result = new LinkedHashMap<>(analysis);
        result.putIfAbsent("filename", file.getOriginalFilename());
        result.put("photoUrl", photoUrl);
        return result;
    }

    /** 치수 분석 없이 사진만 저장 (비박스 수동 등록 등) */
    @PostMapping("/cargo-photo")
    public Map<String, Object> uploadCargoPhoto(@RequestParam("file") MultipartFile file) throws Exception {
        String photoUrl = cargoPhotoStorage.store(file);
        return Map.of("photoUrl", photoUrl, "filename", file.getOriginalFilename());
    }
}
