package com.moveai.backend.controller;

import com.moveai.backend.entity.Truck;
import com.moveai.backend.repository.TruckRepository;
import com.moveai.backend.service.RouteMatchService;
import com.moveai.backend.service.TerminalRegistryService;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.*;

@RestController
@RequestMapping("/api/drivers")
@RequiredArgsConstructor
public class DriverController {

    private final TruckRepository truckRepository;
    private final RouteMatchService routeMatchService;
    private final TerminalRegistryService terminalRegistry;

    @Data
    public static class LoginDto {
        private String phone;
        private String truckNumber;
        private String driverName;
    }

    @Data
    public static class ProfileDto {
        private String driverName;
        private Double capacityTons;
        private Double capacityM3;
        private String vehicleType;
        private Double remainingVolumePercent;
    }

    @Data
    public static class RouteDto {
        private String originCode;
        private String destinationCode;
    }

    @PostMapping("/login")
    public Map<String, Object> login(@RequestBody LoginDto body) {
        String phone = normalizePhone(body.getPhone());
        String truckNumber = normalizeTruck(body.getTruckNumber());
        if (phone.isBlank() || truckNumber.isBlank()) {
            throw new IllegalArgumentException("차량번호와 전화번호를 입력하세요.");
        }

        Truck truck = truckRepository.findByTruckNumberAndPhone(truckNumber, phone).orElse(null);
        boolean isNew = false;
        if (truck == null) {
            isNew = true;
            truck = truckRepository.save(Truck.builder()
                    .phone(phone)
                    .truckNumber(truckNumber)
                    .driverName(body.getDriverName() != null && !body.getDriverName().isBlank()
                            ? body.getDriverName() : "기사")
                    .profileCompleted(false)
                    .status("IDLE")
                    .remainingVolumePercent(100.0)
                    .capacityTons(11.0)
                    .capacityM3(30.545)
                    .vehicleType("윙바디")
                    .currentLat(35.1362)
                    .currentLng(128.8300)
                    .createdAt(LocalDateTime.now())
                    .lastLoginAt(LocalDateTime.now())
                    .build());
        } else {
            truck.setLastLoginAt(LocalDateTime.now());
            if (body.getDriverName() != null && !body.getDriverName().isBlank()) {
                truck.setDriverName(body.getDriverName());
            }
            truckRepository.save(truck);
        }

        Map<String, Object> res = truckView(truck);
        res.put("isNew", isNew);
        res.put("needProfile", truck.getProfileCompleted() == null || !truck.getProfileCompleted());
        res.put("needRoute", truck.getOriginCode() == null || truck.getOriginCode().isBlank()
                || truck.getDestinationCode() == null || truck.getDestinationCode().isBlank());
        res.put("message", isNew ? "신규 기사입니다. 차량 정보를 등록하세요." : "로그인되었습니다.");
        return res;
    }

    @GetMapping("/{id}")
    public Map<String, Object> get(@PathVariable Long id) {
        Truck truck = truckRepository.findById(id)
                .orElseThrow(() -> new NoSuchElementException("기사 없음"));
        Map<String, Object> res = truckView(truck);
        res.put("needProfile", truck.getProfileCompleted() == null || !truck.getProfileCompleted());
        res.put("needRoute", truck.getOriginCode() == null || truck.getOriginCode().isBlank()
                || truck.getDestinationCode() == null || truck.getDestinationCode().isBlank());
        return res;
    }

    @PostMapping("/{id}/profile")
    public Map<String, Object> profile(@PathVariable Long id, @RequestBody ProfileDto body) {
        Truck truck = truckRepository.findById(id)
                .orElseThrow(() -> new NoSuchElementException("기사 없음"));
        if (body.getDriverName() != null && !body.getDriverName().isBlank()) {
            truck.setDriverName(body.getDriverName());
        }
        if (body.getCapacityTons() != null && body.getCapacityTons() > 0) {
            truck.setCapacityTons(body.getCapacityTons());
        }
        if (body.getCapacityM3() != null && body.getCapacityM3() > 0) {
            truck.setCapacityM3(body.getCapacityM3());
        } else if (truck.getCapacityTons() != null) {
            truck.setCapacityM3(RouteMatchService.estimateCapacityM3(truck.getCapacityTons()));
        }
        if (body.getVehicleType() != null && !body.getVehicleType().isBlank()) {
            truck.setVehicleType(body.getVehicleType());
        }
        if (body.getRemainingVolumePercent() != null) {
            truck.setRemainingVolumePercent(body.getRemainingVolumePercent());
        } else if (truck.getRemainingVolumePercent() == null) {
            truck.setRemainingVolumePercent(100.0);
        }
        truck.setProfileCompleted(true);
        truck.setStatus("IDLE");
        truckRepository.save(truck);

        Map<String, Object> res = truckView(truck);
        res.put("needProfile", false);
        res.put("needRoute", truck.getOriginCode() == null || truck.getOriginCode().isBlank()
                || truck.getDestinationCode() == null || truck.getDestinationCode().isBlank());
        res.put("message", "차량 정보가 등록되었습니다.");
        return res;
    }

    /** 작업터미널 코드로 출도착 설정 (관리자와 동일) */
    @PostMapping("/{id}/route")
    public Map<String, Object> route(@PathVariable Long id, @RequestBody RouteDto body) {
        Truck truck = truckRepository.findById(id)
                .orElseThrow(() -> new NoSuchElementException("기사 없음"));
        TerminalRegistryService.Terminal origin = terminalRegistry.findByCode(body.getOriginCode())
                .orElseThrow(() -> new IllegalArgumentException("출발 터미널 없음: " + body.getOriginCode()));
        TerminalRegistryService.Terminal dest = terminalRegistry.findByCode(body.getDestinationCode())
                .orElseThrow(() -> new IllegalArgumentException("도착 터미널 없음: " + body.getDestinationCode()));
        if (origin.code().equalsIgnoreCase(dest.code())) {
            throw new IllegalArgumentException("출발과 도착이 같습니다.");
        }
        truck.setOriginCode(origin.code());
        truck.setDestinationCode(dest.code());
        truck.setOriginName(origin.name());
        truck.setDestinationName(dest.name());
        truck.setCurrentLat(origin.lat());
        truck.setCurrentLng(origin.lng());
        truckRepository.save(truck);

        Map<String, Object> res = truckView(truck);
        res.put("needProfile", truck.getProfileCompleted() == null || !truck.getProfileCompleted());
        res.put("needRoute", false);
        res.put("message", "운행 경로가 설정되었습니다: " + origin.name() + " → " + dest.name());
        return res;
    }

    @GetMapping
    public Map<String, Object> list() {
        List<Map<String, Object>> list = truckRepository.findAll().stream()
                .map(this::truckView)
                .toList();
        return Map.of("drivers", list, "count", list.size());
    }

    private Map<String, Object> truckView(Truck t) {
        double rem = t.getRemainingVolumePercent() != null ? t.getRemainingVolumePercent() : 100.0;
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("truckId", t.getId());
        m.put("driverName", t.getDriverName());
        m.put("phone", t.getPhone());
        m.put("truckNumber", t.getTruckNumber());
        m.put("capacityTons", t.getCapacityTons());
        m.put("capacityM3", t.getCapacityM3() != null ? t.getCapacityM3()
                : RouteMatchService.estimateCapacityM3(t.getCapacityTons() != null ? t.getCapacityTons() : 11));
        m.put("vehicleType", t.getVehicleType());
        m.put("profileCompleted", Boolean.TRUE.equals(t.getProfileCompleted()));
        m.put("originCode", t.getOriginCode());
        m.put("destinationCode", t.getDestinationCode());
        m.put("originName", t.getOriginName());
        m.put("destinationName", t.getDestinationName());
        m.put("currentLat", t.getCurrentLat());
        m.put("currentLng", t.getCurrentLng());
        m.put("remainingVolumePercent", rem);
        m.put("occupiedVolumePercent", Math.round((100.0 - rem) * 100.0) / 100.0);
        m.put("status", t.getStatus());
        m.put("activeRequestId", t.getActiveRequestId());
        return m;
    }

    private String normalizePhone(String phone) {
        if (phone == null) return "";
        return phone.replaceAll("[^0-9]", "");
    }

    private String normalizeTruck(String truck) {
        if (truck == null) return "";
        return truck.replaceAll("\\s+", " ").trim();
    }
}
