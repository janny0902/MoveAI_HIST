# -*- coding: utf-8 -*-
from pathlib import Path

stations = [
    ("BUSAN", "부산터미널(부산역)", "부산광역시 동구 중앙대로 206", 35.1151, 129.0413),
    ("ULSAN", "울산역", "울산광역시 울주군 삼남읍 울산역로 177", 35.5515, 129.1380),
    ("GYEONGJU", "경주(신경주역)", "경상북도 경주시 건천읍 신경주역로 80", 35.6543, 129.2102),
    ("DONGDAEGU", "동대구역", "대구광역시 동구 동대구로 550", 35.8797, 128.6284),
    ("GIMCHEON", "김천(김천구미역)", "경상북도 김천시 남면 혁신1로 57", 36.1135, 128.2700),
    ("DAEJEON", "대전터미널(대전역)", "대전광역시 동구 중앙로 215", 36.3324, 127.4340),
    ("OSONG", "오송역", "충청북도 청주시 흥덕구 오송읍 오송가락로 123", 36.6205, 127.3275),
    ("CHEONAN_ASAN", "천안아산역", "충청남도 아산시 배방읍 희망로 100", 36.7945, 127.1045),
    ("GWANGMYEONG", "광명역", "경기도 광명시 광명역로 21", 37.4164, 126.8848),
    ("SEOUL", "서울터미널(서울역)", "서울특별시 용산구 한강대로 405", 37.5547, 126.9707),
    ("YONGSAN", "용산역", "서울특별시 용산구 한강대로 23길 55", 37.5299, 126.9648),
    ("SUSO", "수서역", "서울특별시 강남구 밤고개로 99", 37.4874, 127.1015),
    ("HAENGSIIN", "행신역", "경기도 고양시 덕양구 소원로 102", 37.6121, 126.8341),
    ("GWANGJU", "광주(광주송정역)", "광주광역시 광산구 상무대로 201", 35.1378, 126.7906),
    ("NAJU", "나주역", "전라남도 나주시 부덕로 159", 35.0142, 126.7171),
    ("MOKPO", "목포역", "전라남도 목포시 영산로 98", 34.7915, 126.3870),
    ("IKSAN", "익산역", "전라북도 익산시 익산대로 153", 35.9403, 126.9450),
    ("JEONJU", "전주역", "전라북도 전주시 덕진구 동부대로 680", 35.8497, 127.1618),
    ("POHANG", "포항역", "경상북도 포항시 북구 흥해읍 포항역로 1", 36.0718, 129.3420),
    ("JINJU", "진주역", "경상남도 진주시 개양로 124", 35.1508, 128.1206),
    ("GANGNEUNG", "강릉역", "강원특별자치도 강릉시 용지로 176", 37.7645, 128.8990),
]


def esc(s: str) -> str:
    return "".join(f"\\u{ord(c):04x}" if ord(c) > 127 else c for c in s)


lines = [
    "package com.moveai.backend.station;",
    "",
    "import java.util.*;",
    "",
    "public final class KtxStations {",
    "",
    "    public record Station(String code, String name, String address, double lat, double lng) {}",
    "",
    "    private static final List<Station> ALL = List.of(",
]
for i, (code, name, addr, lat, lng) in enumerate(stations):
    comma = "," if i < len(stations) - 1 else ""
    lines.append(
        f'            new Station("{code}", "{esc(name)}", "{esc(addr)}", {lat}, {lng}){comma}'
    )
lines += [
    "    );",
    "",
    "    private KtxStations() {}",
    "    public static List<Station> all() { return ALL; }",
    "    public static Optional<Station> findByCode(String code) {",
    "        if (code == null) return Optional.empty();",
    "        return ALL.stream().filter(s -> s.code().equalsIgnoreCase(code)).findFirst();",
    "    }",
    "    public static Optional<Station> findByNameContains(String text) {",
    "        if (text == null || text.isBlank()) return Optional.empty();",
    '        String t = text.replace(" ", "");',
    "        return ALL.stream()",
    '                .filter(s -> s.name().replace(" ", "").contains(t) || t.contains(s.name().replace(" ", "")))',
    "                .findFirst();",
    "    }",
    "}",
    "",
]

Path("backend-spring/src/main/java/com/moveai/backend/station/KtxStations.java").write_text(
    "\n".join(lines), encoding="ascii", newline="\n"
)
print("wrote", len(stations))
