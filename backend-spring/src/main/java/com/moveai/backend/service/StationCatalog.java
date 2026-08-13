package com.moveai.backend.service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class StationCatalog {

    public record Station(String code, String name, String address, double lat, double lng) {}

    private final Map<String, Station> byCode = new LinkedHashMap<>();

    public StationCatalog() {
        // Demo terminals (Busan ↔ Seoul corridor + codes used in docs)
        add("200", "부산터미널", "부산광역시", 35.1152, 129.0415);
        add("201", "부산사상", "부산광역시 사상구", 35.1631, 128.9850);
        add("001", "서울터미널", "서울특별시", 37.4813, 127.0160);
        add("008", "서울동부", "서울특별시 동대문구", 37.5744, 127.0395);
        add("BUSAN", "부산", "부산광역시", 35.1152, 129.0415);
        add("SEOUL", "서울", "서울특별시", 37.4813, 127.0160);
        add("GIMCHEON", "김천", "경상북도 김천시", 36.1220, 128.1150);
    }

    private void add(String code, String name, String address, double lat, double lng) {
        byCode.put(code, new Station(code, name, address, lat, lng));
    }

    public List<Station> all() {
        return List.copyOf(byCode.values());
    }

    public Optional<Station> find(String code) {
        if (code == null) return Optional.empty();
        return Optional.ofNullable(byCode.get(code));
    }
}
