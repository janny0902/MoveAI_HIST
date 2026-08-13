"""기존 체적 운송장을 본떠 대기 운송장을 대량 생성한다.

기존 306건으로는 그룹이 6건짜리로만 나와 "묶어서 배차한다"가 무슨 뜻인지 화면에서
보이지 않는다. 실제 터미널 하나에는 운송장 수천~수만 건이 쌓인다.

만드는 방식:
  * 박스 치수/타입/상품코드는 **기존 306건을 템플릿으로** 삼아 ±흔들어 쓴다. 완전한
    난수로 만들면 체적 분포가 실제 소포와 달라져 적재율이 엉뚱하게 나온다.
  * 출발-도착 터미널 쌍을 먼저 정해 놓고 그 쌍에 배정한다. 쌍을 건마다 무작위로 뽑으면
    122x121 쌍에 흩어져 그룹이 전부 한 자릿수가 된다.
  * 쌍마다 건수를 300~30,000 사이에서 뽑아 합이 목표 건수가 되게 맞춘다.

체적·중량·운임은 **서버와 같은 함수**(waybill_schema)로 계산한다. 여기서 규칙을 다시
쓰면 화면이 서버와 다른 숫자를 말하게 된다.

    python tools/generate_waybills.py --count 100000 --dry-run
    python tools/generate_waybills.py --count 100000 --apply
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "matching-processor"))

from migrate_cargo_terminals import BATCH_LIMIT, DOCS, access_token, api, fetch_all, unwrap

import waybill_schema  # matching-processor와 같은 계산을 쓰기 위해서다

KST = timezone(timedelta(hours=9))

# 그룹 한 덩어리의 크기 범위. 최소를 두는 이유는 300건 밑으로 잘게 쪼개지면 "묶어서
# 배차한다"가 화면에서 보이지 않기 때문이고, 최대를 두는 이유는 한 쌍이 전체를 삼키면
# 그룹이 하나만 남기 때문이다.
MIN_GROUP = 300
MAX_GROUP = 30000


def plan_groups(total: int, pairs_available: int, rng: random.Random) -> list:
    """합이 total이 되는 그룹 크기 목록. 각 원소는 MIN_GROUP..MAX_GROUP."""
    sizes = []
    left = total
    while left >= MIN_GROUP * 2 and len(sizes) < pairs_available - 1:
        # 로그 균등으로 뽑는다. 균등하게 뽑으면 전부 1만5천 근처로 몰려서 큰 묶음과
        # 작은 묶음이 섞인 실제 분포가 안 나온다.
        hi = min(MAX_GROUP, left - MIN_GROUP)
        if hi < MIN_GROUP:
            break
        lo_e, hi_e = 0.0, 1.0
        t = rng.uniform(lo_e, hi_e) ** 2.2  # 작은 쪽으로 치우치게
        size = int(MIN_GROUP + t * (hi - MIN_GROUP))
        sizes.append(size)
        left -= size
    if left > 0:
        # 남은 건수는 마지막 묶음에 넣는다. 상한을 넘으면 쪼갠다.
        while left > MAX_GROUP:
            sizes.append(MAX_GROUP)
            left -= MAX_GROUP
        if left >= MIN_GROUP:
            sizes.append(left)
        elif sizes:
            sizes[-1] += left
        else:
            sizes.append(left)
    return sizes


def jitter_dims(box: dict, rng: random.Random) -> tuple:
    """템플릿 치수를 ±35% 흔든다. 규격 박스라 완전히 자유롭지는 않다."""
    out = []
    for key in ("box_width_mm", "box_depth_mm", "box_height_mm"):
        v = float(box.get(key) or 300.0)
        out.append(max(50.0, round(v * rng.uniform(0.65, 1.35), 1)))
    return tuple(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100000)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=20260810)
    # 구간을 못 박으면 그 한 쌍으로만 만든다. "부산->경주 물량이 이만큼 쌓였을 때
    # 어느 차가 감당하나"처럼 한 구간을 놓고 보는 경우가 있다.
    ap.add_argument("--origin", help="출발 터미널 코드. 지정하면 전량 이 코드로 만든다")
    ap.add_argument("--destination", help="도착 터미널 코드. --origin과 함께 쓴다")
    args = ap.parse_args()
    if bool(args.origin) != bool(args.destination):
        sys.exit("--origin과 --destination은 함께 지정한다.")

    rng = random.Random(args.seed)
    token = access_token()

    terminals = sorted(
        ({k: unwrap(v) for k, v in d["fields"].items()} for d in fetch_all(token, "terminals")),
        key=lambda t: t["terminal_code"],
    )
    if len(terminals) < 2:
        sys.exit("터미널이 2곳 이상 등록돼 있어야 한다.")

    existing = fetch_all(token, "pending_cargos")
    templates = []
    for d in existing:
        f = d["fields"]
        row = {k: unwrap(v) for k, v in f.items()}
        # unwrap은 arrayValue를 {'values': [...]} 그대로 돌려준다. 박스타입은 배열이라
        # 여기서 한 번 더 푼다 — 안 풀면 rng.choice가 dict를 인덱싱하려 든다.
        raw_types = f.get("box_types", {}).get("arrayValue", {}).get("values", [])
        row["box_types"] = [unwrap(v) for v in raw_types]
        if row.get("volume_cbm") and row["box_types"]:
            templates.append(row)
    if not templates:
        sys.exit("템플릿으로 쓸 기존 운송장이 없다.")
    print(f"터미널 {len(terminals)}곳 · 템플릿 {len(templates)}건")

    by_code = {t["terminal_code"]: t for t in terminals}

    if args.origin:
        for code in (args.origin, args.destination):
            if code not in by_code:
                sys.exit(f"터미널 {code}가 등록돼 있지 않다.")
        if args.origin == args.destination:
            sys.exit("출발과 도착이 같을 수 없다.")
        pairs = [(by_code[args.origin], by_code[args.destination])]
        sizes = [args.count]
        print(f"단일 구간 {args.origin}({by_code[args.origin].get('name')}) -> "
              f"{args.destination}({by_code[args.destination].get('name')}) · {args.count}건")
    else:
        # 출발지는 실제로 물량이 몰리는 소수의 허브로 제한한다 — 122곳 전부를 출발지로
        # 쓰면 어느 터미널도 의미 있는 물량을 갖지 못한다.
        hubs = [t for t in terminals[:12]]
        pairs = [(o, d) for o in hubs for d in terminals
                 if o["terminal_code"] != d["terminal_code"]]
        rng.shuffle(pairs)
        sizes = plan_groups(args.count, len(pairs), rng)
        print(f"묶음 {len(sizes)}개 — 최소 {min(sizes)}건 / 최대 {max(sizes)}건 / "
              f"합계 {sum(sizes)}건")

    now = datetime.now(timezone.utc)
    valid_hours = int(os.getenv("WAYBILL_VALID_HOURS", "720"))

    docs = []
    used_ids = set()
    for gi, size in enumerate(sizes):
        origin, dest = pairs[gi]
        for _ in range(size):
            tpl = rng.choice(templates)
            # 운송장번호는 12자리. 중복되면 문서를 덮어써서 건수가 모자란다.
            while True:
                wb = str(rng.randint(300000000000, 399999999999))
                if wb not in used_ids:
                    used_ids.add(wb)
                    break

            box_type = rng.choice(tpl.get("box_types") or ["A"])
            w, dp, h = jitter_dims(
                {"box_width_mm": (tpl["volume_cbm"] * 1e9) ** (1 / 3),
                 "box_depth_mm": (tpl["volume_cbm"] * 1e9) ** (1 / 3),
                 "box_height_mm": (tpl["volume_cbm"] * 1e9) ** (1 / 3)},
                rng,
            )
            volume_cbm = round(w * dp * h / 1e9, 6)
            weight_kg, basis = waybill_schema.estimate_weight_kg(
                volume_cbm, tpl.get("product_code"), box_type
            )
            freight = waybill_schema.freight_krw(box_type)
            fee = round(max(800, freight * 0.0))  # 건당 정액. config의 DRIVER_FEE_PER_BOX_KRW와 같다

            ready = now - timedelta(hours=rng.uniform(0, 48))
            docs.append({
                "cargo_id": wb,
                "volume_cbm": volume_cbm,
                "weight_kg": round(weight_kg, 2),
                "weight_source": "ESTIMATED",
                "weight_basis": basis,
                "pickup_lat": origin["lat"],
                "pickup_lng": origin["lng"],
                "pickup_address": origin.get("address") or origin.get("name"),
                "origin_terminal_code": origin["terminal_code"],
                "origin_terminal_name": origin.get("name"),
                "destination_terminal_code": dest["terminal_code"],
                "destination_terminal_name": dest.get("name"),
                "delivery_lat": dest["lat"],
                "delivery_lng": dest["lng"],
                "delivery_address": dest.get("address") or dest.get("name"),
                "freight_krw": round(freight),
                "commission_krw": fee,
                "revenue_krw": fee,
                "revenue_source": "DRIVER_FEE",
                "box_count": 1,
                "box_types": [box_type],
                "product_code": tpl.get("product_code") or "Box",
                "product_name": tpl.get("product_name") or "박스",
                "status": "WAITING",
                "ready_at": ready,
                "deadline_at": ready + timedelta(hours=valid_hours),
                "registered_at": now,
                "ingest_format": "SYNTHETIC_WAYBILL",
                "ingest_source": f"generate_waybills.py seed={args.seed}",
                "record_type": "SYNTHETIC_WAYBILL_ON_MEASURED_TEMPLATE",
            })

    vols = [d["volume_cbm"] for d in docs]
    print(f"생성 {len(docs)}건 · 체적 합계 {sum(vols):.1f} CBM · "
          f"건당 평균 {sum(vols)/len(vols):.4f} CBM")

    if args.dry_run or not args.apply:
        print("\n--apply 없이는 쓰지 않는다.")
        for d in docs[:3]:
            print(f"  {d['cargo_id']} {d['origin_terminal_code']}->{d['destination_terminal_code']} "
                  f"{d['volume_cbm']}CBM {d['weight_kg']}kg {d['box_types']}")
        return

    def typed(v):
        if isinstance(v, bool):
            return {"booleanValue": v}
        if isinstance(v, int):
            return {"integerValue": str(v)}
        if isinstance(v, float):
            return {"doubleValue": v}
        if isinstance(v, datetime):
            return {"timestampValue": v.astimezone(timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%SZ")}
        if isinstance(v, list):
            return {"arrayValue": {"values": [typed(x) for x in v]}}
        if v is None:
            return {"nullValue": None}
        return {"stringValue": str(v)}

    writes = [{
        "update": {
            "name": f"{DOCS}/pending_cargos/{d['cargo_id']}",
            "fields": {k: typed(v) for k, v in d.items()},
        }
    } for d in docs]

    for i in range(0, len(writes), BATCH_LIMIT):
        api(token, f"{DOCS}:batchWrite", {"writes": writes[i:i + BATCH_LIMIT]}, method="POST")
        print(f"\r  적재 {min(i + BATCH_LIMIT, len(writes))}/{len(writes)}", end="", flush=True)
    print("\n완료")


if __name__ == "__main__":
    main()
