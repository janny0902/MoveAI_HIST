"""터미널 코드가 없는 구 합성 화물을 pending_cargos에서 지운다.

pending_cargos에는 성격이 다른 두 데이터가 섞여 있었다.

  * 체적 운송장 — 측정기 CSV 적재분. origin/destination 작업터미널을 갖는다.
  * 구 합성 화물 — record_type=SYNTHETIC_PENDING_CARGO. 운송장 체계 이전 데이터로
    터미널 코드가 없고 pickup_hub/delivery_hub 문자열만 있다.

둘 다 status=WAITING에 좌표가 있어 매칭 후보로 함께 잡힌다. 그래서 결과를 출발-도착
터미널로 묶으면 구 합성 화물이 전부 '미지정' 그룹으로 쏟아져 그룹화가 무의미해진다.
후보 모수를 한 체계로 통일한다.

    python tools/prune_legacy_cargos.py --dry-run
    python tools/prune_legacy_cargos.py --apply
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from migrate_cargo_terminals import BATCH_LIMIT, DOCS, access_token, api, fetch_all

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup", default=os.path.join(HERE, "legacy_cargos_backup.json"))
    args = ap.parse_args()

    token = access_token()
    docs = fetch_all(token, "pending_cargos")

    # 판정 기준은 '출발 터미널이 없다' 하나다. record_type으로 고르지 않는 이유는,
    # 앞으로 들어올 합성 데이터가 터미널을 갖고 있으면 지울 이유가 없기 때문이다.
    legacy = [d for d in docs if "origin_terminal_code" not in d["fields"]]
    keep = len(docs) - len(legacy)
    print(f"pending_cargos {len(docs)}건 — 삭제 대상 {len(legacy)}건 / 유지 {keep}건")

    if legacy:
        f = legacy[0]["fields"]
        g = lambda k: list(f[k].values())[0] if k in f else "-"
        print(f"  예시 {g('cargo_id')} | record_type={g('record_type')} "
              f"| pickup_hub={g('pickup_hub')} -> delivery_hub={g('delivery_hub')}")

    if args.dry_run or not args.apply:
        print("\n--apply 없이는 지우지 않는다.")
        return
    if not legacy:
        print("지울 문서가 없다.")
        return

    with open(args.backup, "w", encoding="utf-8") as fp:
        json.dump(legacy, fp, ensure_ascii=False)
    print(f"백업 저장: {args.backup}")

    writes = [{"delete": d["name"]} for d in legacy]
    for i in range(0, len(writes), BATCH_LIMIT):
        api(token, f"{DOCS}:batchWrite", {"writes": writes[i:i + BATCH_LIMIT]},
            method="POST")
        print(f"\r  삭제 {min(i + BATCH_LIMIT, len(writes))}/{len(writes)}",
              end="", flush=True)

    left = fetch_all(token, "pending_cargos")
    print(f"\n완료 — pending_cargos {len(left)}건 남음")


if __name__ == "__main__":
    main()
