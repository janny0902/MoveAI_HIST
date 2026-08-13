package com.moveai.backend.station;

import java.util.*;

public final class KtxStations {

    public record Station(String code, String name, String address, double lat, double lng) {}

    private static final List<Station> ALL = List.of(
            new Station("BUSAN", "\ubd80\uc0b0\ud130\ubbf8\ub110(\ubd80\uc0b0\uc5ed)", "\ubd80\uc0b0\uad11\uc5ed\uc2dc \ub3d9\uad6c \uc911\uc559\ub300\ub85c 206", 35.1151, 129.0413),
            new Station("ULSAN", "\uc6b8\uc0b0\uc5ed", "\uc6b8\uc0b0\uad11\uc5ed\uc2dc \uc6b8\uc8fc\uad70 \uc0bc\ub0a8\uc74d \uc6b8\uc0b0\uc5ed\ub85c 177", 35.5515, 129.138),
            new Station("GYEONGJU", "\uacbd\uc8fc(\uc2e0\uacbd\uc8fc\uc5ed)", "\uacbd\uc0c1\ubd81\ub3c4 \uacbd\uc8fc\uc2dc \uac74\ucc9c\uc74d \uc2e0\uacbd\uc8fc\uc5ed\ub85c 80", 35.6543, 129.2102),
            new Station("DONGDAEGU", "\ub3d9\ub300\uad6c\uc5ed", "\ub300\uad6c\uad11\uc5ed\uc2dc \ub3d9\uad6c \ub3d9\ub300\uad6c\ub85c 550", 35.8797, 128.6284),
            new Station("GIMCHEON", "\uae40\ucc9c(\uae40\ucc9c\uad6c\ubbf8\uc5ed)", "\uacbd\uc0c1\ubd81\ub3c4 \uae40\ucc9c\uc2dc \ub0a8\uba74 \ud601\uc2e01\ub85c 57", 36.1135, 128.27),
            new Station("DAEJEON", "\ub300\uc804\ud130\ubbf8\ub110(\ub300\uc804\uc5ed)", "\ub300\uc804\uad11\uc5ed\uc2dc \ub3d9\uad6c \uc911\uc559\ub85c 215", 36.3324, 127.434),
            new Station("OSONG", "\uc624\uc1a1\uc5ed", "\ucda9\uccad\ubd81\ub3c4 \uccad\uc8fc\uc2dc \ud765\ub355\uad6c \uc624\uc1a1\uc74d \uc624\uc1a1\uac00\ub77d\ub85c 123", 36.6205, 127.3275),
            new Station("CHEONAN_ASAN", "\ucc9c\uc548\uc544\uc0b0\uc5ed", "\ucda9\uccad\ub0a8\ub3c4 \uc544\uc0b0\uc2dc \ubc30\ubc29\uc74d \ud76c\ub9dd\ub85c 100", 36.7945, 127.1045),
            new Station("GWANGMYEONG", "\uad11\uba85\uc5ed", "\uacbd\uae30\ub3c4 \uad11\uba85\uc2dc \uad11\uba85\uc5ed\ub85c 21", 37.4164, 126.8848),
            new Station("SEOUL", "\uc11c\uc6b8\ud130\ubbf8\ub110(\uc11c\uc6b8\uc5ed)", "\uc11c\uc6b8\ud2b9\ubcc4\uc2dc \uc6a9\uc0b0\uad6c \ud55c\uac15\ub300\ub85c 405", 37.5547, 126.9707),
            new Station("YONGSAN", "\uc6a9\uc0b0\uc5ed", "\uc11c\uc6b8\ud2b9\ubcc4\uc2dc \uc6a9\uc0b0\uad6c \ud55c\uac15\ub300\ub85c 23\uae38 55", 37.5299, 126.9648),
            new Station("SUSO", "\uc218\uc11c\uc5ed", "\uc11c\uc6b8\ud2b9\ubcc4\uc2dc \uac15\ub0a8\uad6c \ubc24\uace0\uac1c\ub85c 99", 37.4874, 127.1015),
            new Station("HAENGSIIN", "\ud589\uc2e0\uc5ed", "\uacbd\uae30\ub3c4 \uace0\uc591\uc2dc \ub355\uc591\uad6c \uc18c\uc6d0\ub85c 102", 37.6121, 126.8341),
            new Station("GWANGJU", "\uad11\uc8fc(\uad11\uc8fc\uc1a1\uc815\uc5ed)", "\uad11\uc8fc\uad11\uc5ed\uc2dc \uad11\uc0b0\uad6c \uc0c1\ubb34\ub300\ub85c 201", 35.1378, 126.7906),
            new Station("NAJU", "\ub098\uc8fc\uc5ed", "\uc804\ub77c\ub0a8\ub3c4 \ub098\uc8fc\uc2dc \ubd80\ub355\ub85c 159", 35.0142, 126.7171),
            new Station("MOKPO", "\ubaa9\ud3ec\uc5ed", "\uc804\ub77c\ub0a8\ub3c4 \ubaa9\ud3ec\uc2dc \uc601\uc0b0\ub85c 98", 34.7915, 126.387),
            new Station("IKSAN", "\uc775\uc0b0\uc5ed", "\uc804\ub77c\ubd81\ub3c4 \uc775\uc0b0\uc2dc \uc775\uc0b0\ub300\ub85c 153", 35.9403, 126.945),
            new Station("JEONJU", "\uc804\uc8fc\uc5ed", "\uc804\ub77c\ubd81\ub3c4 \uc804\uc8fc\uc2dc \ub355\uc9c4\uad6c \ub3d9\ubd80\ub300\ub85c 680", 35.8497, 127.1618),
            new Station("POHANG", "\ud3ec\ud56d\uc5ed", "\uacbd\uc0c1\ubd81\ub3c4 \ud3ec\ud56d\uc2dc \ubd81\uad6c \ud765\ud574\uc74d \ud3ec\ud56d\uc5ed\ub85c 1", 36.0718, 129.342),
            new Station("JINJU", "\uc9c4\uc8fc\uc5ed", "\uacbd\uc0c1\ub0a8\ub3c4 \uc9c4\uc8fc\uc2dc \uac1c\uc591\ub85c 124", 35.1508, 128.1206),
            new Station("GANGNEUNG", "\uac15\ub989\uc5ed", "\uac15\uc6d0\ud2b9\ubcc4\uc790\uce58\ub3c4 \uac15\ub989\uc2dc \uc6a9\uc9c0\ub85c 176", 37.7645, 128.899)
    );

    private KtxStations() {}
    public static List<Station> all() { return ALL; }
    private static final List<String> GYENGBU = List.of(
            "BUSAN", "ULSAN", "GYEONGJU", "DONGDAEGU", "GIMCHEON",
            "DAEJEON", "OSONG", "CHEONAN_ASAN", "GWANGMYEONG", "SEOUL", "YONGSAN"
    );

    public static List<String> gyeongbuCodes() {
        return GYENGBU;
    }

    /** 시연용: 현재 역에서 기사 목적지 방향의 다음 경부축 역 */
    public static Optional<Station> nextToward(String fromCode, String driverDestCode) {
        int from = indexOfGyeongbu(fromCode);
        int dest = indexOfGyeongbu(driverDestCode != null ? driverDestCode : "SEOUL");
        if (from < 0) return findByCode("SEOUL");
        if (dest < 0) dest = indexOfGyeongbu("SEOUL");
        if (from == dest) return findByCode(fromCode);
        int step = dest >= from ? 1 : -1;
        int next = from + step;
        if (next < 0 || next >= GYENGBU.size()) return findByCode(GYENGBU.get(from));
        // 목적지를 넘지 않음
        if (step > 0 && next > dest) next = dest;
        if (step < 0 && next < dest) next = dest;
        return findByCode(GYENGBU.get(next));
    }

    private static int indexOfGyeongbu(String code) {
        if (code == null) return -1;
        for (int i = 0; i < GYENGBU.size(); i++) {
            if (GYENGBU.get(i).equalsIgnoreCase(code)) return i;
        }
        return -1;
    }

    public static Optional<Station> findByCode(String code) {
        if (code == null) return Optional.empty();
        return ALL.stream().filter(s -> s.code().equalsIgnoreCase(code)).findFirst();
    }
    public static Optional<Station> findByNameContains(String text) {
        if (text == null || text.isBlank()) return Optional.empty();
        String t = text.replace(" ", "");
        return ALL.stream()
                .filter(s -> s.name().replace(" ", "").contains(t) || t.contains(s.name().replace(" ", "")))
                .findFirst();
    }

    /** 위경도 → 가장 가까운 KTX/터미널 스테이션 (관리자 터미널 매핑용) */
    public static Station nearest(double lat, double lng) {
        Station best = ALL.get(0);
        double bestD = Double.MAX_VALUE;
        for (Station s : ALL) {
            double d = haversine(lat, lng, s.lat(), s.lng());
            if (d < bestD) {
                bestD = d;
                best = s;
            }
        }
        return best;
    }

    public static double haversine(double lat1, double lng1, double lat2, double lng2) {
        double R = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }
}
