package com.moveai.backend.service;

import com.moveai.backend.entity.Truck;
import com.moveai.backend.repository.TruckRepository;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DriverService {
    private final TruckRepository truckRepository;
    private final StationCatalog stations;

    public DriverService(TruckRepository truckRepository, StationCatalog stations) {
        this.truckRepository = truckRepository;
        this.stations = stations;
    }

    @Transactional
    public Map<String, Object> login(String phone, String truckNumber, String driverName) {
        boolean isNew = false;
        Truck truck = truckRepository.findByPhoneAndTruckNumber(phone, truckNumber).orElse(null);
        if (truck == null) {
            truck = new Truck();
            truck.setPhone(phone);
            truck.setTruckNumber(truckNumber);
            truck.setDriverName(driverName != null && !driverName.isBlank() ? driverName : "기사");
            truck = truckRepository.save(truck);
            isNew = true;
        } else if (driverName != null && !driverName.isBlank()) {
            truck.setDriverName(driverName);
            truck = truckRepository.save(truck);
        }
        return wrap(truck, isNew, isNew ? "신규 기사 등록" : "로그인 성공");
    }

    @Transactional(readOnly = true)
    public Map<String, Object> get(Long id) {
        Truck truck = require(id);
        return wrap(truck, false, "ok");
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list() {
        List<Map<String, Object>> drivers = truckRepository.findAll().stream()
                .map(this::truckView)
                .toList();
        return Map.of("drivers", drivers, "count", drivers.size());
    }

    @Transactional
    public Map<String, Object> updateProfile(Long id, Map<String, Object> body) {
        Truck truck = require(id);
        if (body.get("driverName") != null) truck.setDriverName(String.valueOf(body.get("driverName")));
        if (body.get("capacityTons") != null) truck.setCapacityTons(toDouble(body.get("capacityTons")));
        if (body.get("capacityM3") != null) truck.setCapacityM3(toDouble(body.get("capacityM3")));
        if (body.get("vehicleType") != null) truck.setVehicleType(String.valueOf(body.get("vehicleType")));
        if (body.get("remainingVolumePercent") != null) {
            truck.setRemainingVolumePercent(toDouble(body.get("remainingVolumePercent")));
        }
        truck.setProfileCompleted(true);
        return wrap(truckRepository.save(truck), false, "프로필 저장");
    }

    @Transactional
    public Map<String, Object> updateRoute(Long id, String originCode, String destinationCode) {
        Truck truck = require(id);
        StationCatalog.Station origin = stations.find(originCode)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.BAD_REQUEST, "unknown origin"));
        StationCatalog.Station dest = stations.find(destinationCode)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.BAD_REQUEST, "unknown destination"));
        truck.setOriginCode(origin.code());
        truck.setOriginName(origin.name());
        truck.setDestinationCode(dest.code());
        truck.setDestinationName(dest.name());
        truck.setCurrentLocationLat(origin.lat());
        truck.setCurrentLocationLng(origin.lng());
        return wrap(truckRepository.save(truck), false, "출도착 저장");
    }

    private Truck require(Long id) {
        return truckRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "truck not found"));
    }

    private Map<String, Object> wrap(Truck truck, boolean isNew, String message) {
        Map<String, Object> res = new HashMap<>(truckView(truck));
        res.put("isNew", isNew);
        res.put("needProfile", !Boolean.TRUE.equals(truck.getProfileCompleted()));
        res.put("needRoute", truck.getOriginCode() == null || truck.getDestinationCode() == null);
        res.put("message", message);
        return res;
    }

    private Map<String, Object> truckView(Truck t) {
        double rem = t.getRemainingVolumePercent() == null ? 100.0 : t.getRemainingVolumePercent();
        Map<String, Object> m = new HashMap<>();
        m.put("truckId", t.getId());
        m.put("driverName", t.getDriverName());
        m.put("phone", t.getPhone());
        m.put("truckNumber", t.getTruckNumber());
        m.put("capacityTons", t.getCapacityTons());
        m.put("capacityM3", t.getCapacityM3());
        m.put("vehicleType", t.getVehicleType());
        m.put("profileCompleted", Boolean.TRUE.equals(t.getProfileCompleted()));
        m.put("originCode", t.getOriginCode());
        m.put("originName", t.getOriginName());
        m.put("destinationCode", t.getDestinationCode());
        m.put("destinationName", t.getDestinationName());
        m.put("remainingVolumePercent", rem);
        m.put("occupiedVolumePercent", Math.max(0, 100.0 - rem));
        m.put("status", t.getStatus());
        return m;
    }

    private static double toDouble(Object v) {
        if (v instanceof Number n) return n.doubleValue();
        return Double.parseDouble(String.valueOf(v));
    }
}
