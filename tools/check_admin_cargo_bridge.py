#!/usr/bin/env python3
"""관리자 matching API → 기사 복화 매핑 점검 (배포 없이 데이터 확인)."""
from __future__ import annotations

import json
import math
import urllib.request

MATCHING = "https://matching-processor-xi6ooeq3ta-du.a.run.app"

KTX = [
    ("BUSAN", 35.1151, 129.0413),
    ("ULSAN", 35.5515, 129.138),
    ("DONGDAEGU", 35.8797, 128.6284),
    ("DAEJEON", 36.3324, 127.434),
    ("SEOUL", 37.5547, 126.9707),
    ("GWANGJU", 35.1378, 126.7906),
]


def get(path: str):
    with urllib.request.urlopen(MATCHING + path, timeout=60) as r:
        return json.load(r)


def hav(a, b):
    R = 6371.0
    lat1, lng1 = a
    lat2, lng2 = b
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    x = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def nearest(lat, lng):
    best = KTX[0]
    best_d = 1e9
    for code, la, ln in KTX:
        d = hav((lat, lng), (la, ln))
        if d < best_d:
            best_d = d
            best = (code, la, ln)
    return best[0], best_d


def main():
    cargos = get("/v1/cargos?limit=1&page=1")
    print("=== matching cargos ===")
    print("total=", cargos.get("total"), "sample_id=", cargos["cargos"][0]["cargo_id"])

    terms = get("/v1/terminals")["terminals"]
    print("terminals=", len(terms))

    term_xy = {t["terminal_code"]: (t.get("lat") or 0, t.get("lng") or 0, t.get("name")) for t in terms}

    busan = get("/v1/cargos?limit=200&page=1&terminal_code=200")["cargos"]
    print("\n=== BUSAN(200) OD groups (not 1-box) ===")
    from collections import defaultdict
    groups = defaultdict(lambda: {"n": 0, "boxes": 0, "cbm": 0.0, "fee": 0})
    for c in busan:
        k = (c["origin_terminal_code"], c["destination_terminal_code"])
        groups[k]["n"] += 1
        groups[k]["boxes"] += c.get("box_count") or 1
        groups[k]["cbm"] += c.get("volume_cbm") or 0
        groups[k]["fee"] += c.get("freight_krw") or 0
    print("fetched", len(busan), "OD groups", len(groups))
    for (o, d), v in sorted(groups.items(), key=lambda x: -x[1]["cbm"])[:10]:
        print(
            f"  {o}->{d} waybills={v['n']} boxes={v['boxes']} "
            f"cbm={v['cbm']:.3f} fee={v['fee']} fill%={v['cbm']/50*100:.2f}"
        )

    print("\n=== sample map to KTX (first 5 waybills) ===")
    mapped = []
    for c in busan[:5]:
        o = c["origin_terminal_code"]
        d = c["destination_terminal_code"]
        olat = c.get("pickup_lat") or term_xy.get(o, (0, 0))[0]
        olng = c.get("pickup_lng") or term_xy.get(o, (0, 0))[1]
        dlat, dlng, _ = term_xy.get(d, (0, 0, None))
        o_ktx, _ = nearest(olat, olng) if olat else ("?", 0)
        d_ktx, _ = nearest(dlat, dlng) if dlat else ("?", 0)
        fill = round(c["volume_cbm"] / 50 * 100, 2)
        mapped.append((c["cargo_id"], o, d, o_ktx, d_ktx, c["volume_cbm"], fill, c.get("freight_krw")))
        print(
            f"{c['cargo_id']} {o}->{d}  KTX {o_ktx}->{d_ktx}  "
            f"cbm={c['volume_cbm']:.4f} fill%={fill} fee={c.get('freight_krw')}"
        )

    # 기사 BUSAN→SEOUL 기준 onRoute 대략: 둘 다 경부축
    corridor = {"BUSAN", "ULSAN", "DONGDAEGU", "DAEJEON", "SEOUL"}
    on = [m for m in mapped if m[3] in corridor and m[4] in corridor]
    print(f"\nonRoute-ish for BUSAN→SEOUL: {len(on)}/{len(mapped)}")

    trucks = get("/v1/trucks") if False else None
    # vision trucks
    try:
        with urllib.request.urlopen("https://vision-processor-xi6ooeq3ta-du.a.run.app/v1/trucks", timeout=30) as r:
            trucks = json.load(r)
        print("\n=== vision trucks ===")
        for t in trucks.get("trucks", [])[:5]:
            print(t["truck_id"], t.get("model"), "cbm", t.get("capacity_cbm"))
    except Exception as e:
        print("trucks fail", e)

    print("\nOK: matching data reachable; bridge can upsert these into cargo_requests")


if __name__ == "__main__":
    main()
