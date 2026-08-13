package com.moveai.backend.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

import java.net.URI;
import java.util.*;

/** 카카오 로컬 키워드 검색 — 터미널 주소 → GPS */
@Slf4j
@Service
public class KakaoLocalService {

    public record GeoHit(double lat, double lng, String address, String placeName) {}

    private final RestTemplate restTemplate;

    @Value("${kakao.rest.key:}")
    private String kakaoRestKey;

    public KakaoLocalService(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public Optional<GeoHit> searchFirst(String query) {
        if (query == null || query.isBlank()) return Optional.empty();
        if (kakaoRestKey == null || kakaoRestKey.isBlank()) {
            log.warn("KAKAO_REST_KEY empty — local search skipped");
            return Optional.empty();
        }
        try {
            URI uri = UriComponentsBuilder
                    .fromUriString("https://dapi.kakao.com/v2/local/search/keyword.json")
                    .queryParam("query", query.trim())
                    .queryParam("size", 1)
                    .build()
                    .encode()
                    .toUri();
            HttpHeaders headers = new HttpHeaders();
            headers.set("Authorization", "KakaoAK " + kakaoRestKey.trim());
            headers.setAccept(List.of(MediaType.APPLICATION_JSON));
            ResponseEntity<Map> res = restTemplate.exchange(
                    uri, HttpMethod.GET, new HttpEntity<>(headers), Map.class);
            Map body = res.getBody();
            if (body == null) return Optional.empty();
            Object docs = body.get("documents");
            if (!(docs instanceof List<?> list) || list.isEmpty()) return Optional.empty();
            Object first = list.get(0);
            if (!(first instanceof Map<?, ?> m)) return Optional.empty();
            double lng = Double.parseDouble(String.valueOf(m.get("x")));
            double lat = Double.parseDouble(String.valueOf(m.get("y")));
            String addr = str(m.get("road_address_name"));
            if (addr.isBlank()) addr = str(m.get("address_name"));
            String place = str(m.get("place_name"));
            return Optional.of(new GeoHit(lat, lng, addr, place));
        } catch (Exception e) {
            log.warn("kakao local search failed for '{}': {}", query, e.toString());
            return Optional.empty();
        }
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o).trim();
    }
}
