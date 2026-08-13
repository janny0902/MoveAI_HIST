package com.moveai.backend.service;

import com.moveai.backend.station.KtxStations;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 관리자 matching 작업터미널 = 기사 출도착 단일 소스.
 * GPS는 matching 값 또는 카카오 로컬 검색 보정 캐시.
 */
@Slf4j
@Service
public class TerminalRegistryService {

    public record Terminal(String code, String name, String address, double lat, double lng) {
        public KtxStations.Station asStation() {
            return new KtxStations.Station(code, name, address != null ? address : name, lat, lng);
        }

        public Map<String, Object> toMap() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("code", code);
            m.put("name", name);
            m.put("address", address);
            m.put("lat", lat);
            m.put("lng", lng);
            return m;
        }
    }

    private final RestTemplate adminProxyRestTemplate;
    private final KakaoLocalService kakaoLocalService;

    @Value("${admin.matching.base-url:https://matching-processor-xi6ooeq3ta-du.a.run.app}")
    private String matchingBaseUrl;

    /** code → GPS 보정 좌표 (메모리) */
    private final ConcurrentHashMap<String, double[]> gpsOverrides = new ConcurrentHashMap<>();
    private volatile List<Terminal> cached = List.of();
    private volatile long cachedAtMs = 0;

    public TerminalRegistryService(
            @Qualifier("adminProxyRestTemplate") RestTemplate adminProxyRestTemplate,
            KakaoLocalService kakaoLocalService
    ) {
        this.adminProxyRestTemplate = adminProxyRestTemplate;
        this.kakaoLocalService = kakaoLocalService;
    }

    public List<Terminal> listTerminals() {
        ensureLoaded(false);
        return cached;
    }

    /** 기동 시 즉시 시드만 채움(블로킹 최소화). matching은 refreshAsync로 갱신. */
    public int warmOnStartup() {
        if (cached.isEmpty()) {
            cached = fallbackSeed();
            cachedAtMs = System.currentTimeMillis();
        }
        return cached.size();
    }

    /** matching 비동기 갱신 — 실패해도 시드 유지 */
    public void refreshAsync() {
        Thread t = new Thread(() -> {
            try {
                List<Terminal> fresh = fetchFromMatching();
                if (fresh.isEmpty()) return;
                List<Terminal> withOverride = new ArrayList<>();
                for (Terminal term : fresh) {
                    if (gpsOverrides.containsKey(term.code())) {
                        double[] ll = gpsOverrides.get(term.code());
                        withOverride.add(new Terminal(term.code(), term.name(), term.address(), ll[0], ll[1]));
                    } else {
                        withOverride.add(term);
                    }
                }
                withOverride.sort(Comparator.comparing(Terminal::code));
                cached = List.copyOf(withOverride);
                cachedAtMs = System.currentTimeMillis();
                log.info("terminal cache refreshed from matching: {} entries", cached.size());
            } catch (Exception e) {
                log.warn("async matching refresh skipped: {}", e.toString());
            }
        }, "terminal-refresh");
        t.setDaemon(true);
        t.start();
    }

    public Optional<Terminal> findByCode(String code) {
        if (code == null || code.isBlank()) return Optional.empty();
        ensureLoaded(false);
        return cached.stream().filter(t -> t.code().equalsIgnoreCase(code.trim())).findFirst();
    }

    /** matching 재조회 + (옵션) 카카오 GPS 보정 */
    public Map<String, Object> refresh(boolean refreshGps) {
        List<Terminal> fresh = fetchFromMatching();
        if (fresh.isEmpty() && !cached.isEmpty()) {
            fresh = new ArrayList<>(cached);
        }
        int gpsOk = 0;
        int gpsFail = 0;
        List<Terminal> out = new ArrayList<>();
        for (Terminal t : fresh) {
            Terminal resolved = t;
            if (refreshGps) {
                String query = (t.address() != null && !t.address().isBlank())
                        ? t.address()
                        : (t.name() != null ? t.name().replace("(가상)", "").trim() : t.code());
                Optional<KakaoLocalService.GeoHit> hit = kakaoLocalService.searchFirst(query);
                if (hit.isEmpty() && t.name() != null) {
                    hit = kakaoLocalService.searchFirst(t.name().replace("(가상)", "").trim());
                }
                if (hit.isPresent()) {
                    KakaoLocalService.GeoHit h = hit.get();
                    gpsOverrides.put(t.code(), new double[]{h.lat(), h.lng()});
                    String addr = h.address() != null && !h.address().isBlank() ? h.address() : t.address();
                    resolved = new Terminal(t.code(), t.name(), addr, h.lat(), h.lng());
                    gpsOk++;
                } else {
                    gpsFail++;
                }
            } else if (gpsOverrides.containsKey(t.code())) {
                double[] ll = gpsOverrides.get(t.code());
                resolved = new Terminal(t.code(), t.name(), t.address(), ll[0], ll[1]);
            }
            out.add(resolved);
        }
        out.sort(Comparator.comparing(Terminal::code));
        cached = List.copyOf(out);
        cachedAtMs = System.currentTimeMillis();

        Map<String, Object> res = new LinkedHashMap<>();
        res.put("count", cached.size());
        res.put("gpsRefreshed", refreshGps);
        res.put("gpsOk", gpsOk);
        res.put("gpsFail", gpsFail);
        res.put("terminals", cached.stream().map(Terminal::toMap).toList());
        return res;
    }

    private void ensureLoaded(boolean force) {
        // 빈 캐시면 matching 대기 전에 시드부터 — 재시작 직후 드롭다운 공백 방지
        if (cached.isEmpty()) {
            synchronized (this) {
                if (cached.isEmpty()) {
                    cached = fallbackSeed();
                    cachedAtMs = System.currentTimeMillis();
                }
            }
        }
        if (!force && !cached.isEmpty() && System.currentTimeMillis() - cachedAtMs < 10 * 60_000L) {
            return;
        }
        synchronized (this) {
            if (!force && !cached.isEmpty() && System.currentTimeMillis() - cachedAtMs < 10 * 60_000L) {
                return;
            }
            List<Terminal> fresh = fetchFromMatching();
            if (fresh.isEmpty()) {
                if (cached.isEmpty()) {
                    cached = fallbackSeed();
                }
            } else {
                List<Terminal> withOverride = new ArrayList<>();
                for (Terminal t : fresh) {
                    if (gpsOverrides.containsKey(t.code())) {
                        double[] ll = gpsOverrides.get(t.code());
                        withOverride.add(new Terminal(t.code(), t.name(), t.address(), ll[0], ll[1]));
                    } else {
                        withOverride.add(t);
                    }
                }
                withOverride.sort(Comparator.comparing(Terminal::code));
                cached = List.copyOf(withOverride);
            }
            cachedAtMs = System.currentTimeMillis();
        }
    }

    private List<Terminal> fetchFromMatching() {
        try {
            String url = matchingBaseUrl.replaceAll("/$", "") + "/v1/terminals";
            ResponseEntity<Map<String, Object>> res = adminProxyRestTemplate.exchange(
                    url, HttpMethod.GET, null,
                    new ParameterizedTypeReference<>() {}
            );
            Object raw = res.getBody() != null ? res.getBody().get("terminals") : null;
            if (!(raw instanceof List<?> list)) return List.of();
            List<Terminal> out = new ArrayList<>();
            for (Object o : list) {
                if (!(o instanceof Map<?, ?> m)) continue;
                String code = str(m.get("terminal_code"));
                if (code.isBlank()) code = str(m.get("code"));
                if (code.isBlank()) continue;
                String name = str(m.get("name"));
                if (name.isBlank()) name = code;
                String address = str(m.get("address"));
                double lat = num(m.get("lat"), 0);
                double lng = num(m.get("lng"), 0);
                out.add(new Terminal(code, name, address, lat, lng));
            }
            return out;
        } catch (Exception e) {
            log.warn("terminal fetch failed: {}", e.toString());
            return List.of();
        }
    }

    /** matching 장애 시 시연용 최소 시드 (부산→서울 축 포함) */
    private List<Terminal> fallbackSeed() {
        return List.of(
                new Terminal("200", "부산강서터미널", "부산광역시 강서구", 35.1362, 128.8300),
                new Terminal("201", "부산사상터미널", "부산광역시 사상구", 35.1526, 128.9910),
                new Terminal("300", "대구북구터미널", "대구광역시 북구", 35.8858, 128.5828),
                new Terminal("308", "김천터미널", "경상북도 김천시", 36.1398, 128.1136),
                new Terminal("500", "대전대덕터미널", "대전광역시 대덕구", 36.4194, 127.4310),
                new Terminal("501", "대전유성터미널", "대전광역시 유성구", 36.4102, 127.3894),
                new Terminal("503", "천안터미널", "충청남도 천안시", 36.8151, 127.1139),
                new Terminal("514", "진천터미널", "충청북도 진천군", 36.8555, 127.4356),
                new Terminal("001", "서울동부터미널", "서울특별시 동대문구", 37.5745, 127.0555),
                new Terminal("008", "서울강남터미널", "서울특별시 강남구", 37.5172, 127.0473)
        );
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
}
