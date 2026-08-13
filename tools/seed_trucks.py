"""trucks 컬렉션을 CSV 한 장으로 갈아끼운다.

기존 100,000대 합성 데이터는 톤급 분포를 보려고 만든 것이고, 시연에서는 톤급별
대표 1대씩만 있으면 된다. 대수가 많으면 차량 선택 목록이 쓸모없어지는 데다,
어떤 차로 찍었는지에 따라 결과가 달라져 재현이 안 된다.

    python tools/seed_trucks.py --dry-run     # 무엇이 지워지고 무엇이 들어가는지만
    python tools/seed_trucks.py --backup-only # 백업 JSON만 만든다
    python tools/seed_trucks.py --apply       # 실제로 갈아끼운다

적재중량은 CSV 값과 무관하게 항상 0으로 넣는다. 시연은 빈 차에서 시작하고,
current_loaded_weight_kg가 0이 아니면 available_payload_kg가 줄어 매칭 결과가
차량마다 달라진다(main.py의 적재중량 제약).
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

PROJECT = os.getenv("GCP_PROJECT", "moveai-504903")
BASE = (f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
        "/databases/(default)/documents")
COLLECTION = "trucks"

# Firestore batchWrite 한 번에 담을 수 있는 최대 연산 수.
BATCH_LIMIT = 500

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "trucks_seed.csv")

INT_FIELDS = {"registered_year", "max_payload_kg", "current_loaded_weight_kg",
              "available_payload_kg"}
FLOAT_FIELDS = {"cargo_width_m", "cargo_length_m", "cargo_height_m",
                "cargo_capacity_cbm", "current_lat", "current_lng",
                "destination_lat", "destination_lng", "load_ratio"}


def access_token() -> str:
    """gcloud가 PATH에 없는 환경(Windows 압축 해제 설치)도 있어 lib/gcloud.py로 떨어진다."""
    for cmd in (["gcloud", "auth", "print-access-token"],
                [sys.executable,
                 os.path.expandvars(r"%LOCALAPPDATA%\Google\Cloud SDK"
                                    r"\google-cloud-sdk\lib\gcloud.py"),
                 "auth", "print-access-token"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return out.stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    sys.exit("gcloud 액세스 토큰을 얻지 못했다. gcloud auth login을 먼저 실행한다.")


def api(token: str, path: str, payload=None, method="GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"https://firestore.googleapis.com/v1/{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req))
        except urllib.error.HTTPError as e:
            # 429/503은 대량 쓰기에서 정상적으로 나온다. 지수 백오프로 되민다.
            if e.code in (429, 500, 503) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"Firestore {method} {path} 실패 {e.code}: {e.read().decode()[:400]}")
    return None


def typed(field: str, raw: str) -> dict:
    """CSV 문자열을 Firestore 값 래퍼로 바꾼다. 타입이 섞이면 쿼리가 안 걸린다."""
    if field in INT_FIELDS:
        return {"integerValue": str(int(float(raw)))}
    if field in FLOAT_FIELDS:
        return {"doubleValue": float(raw)}
    return {"stringValue": raw}


def load_rows() -> list:
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        r = {k: v for k, v in r.items() if v != ""}
        # 시연은 빈 차에서 시작한다. CSV에 뭐가 적혀 있든 0으로 못 박는다.
        r["current_loaded_weight_kg"] = "0"
        r["available_payload_kg"] = r["max_payload_kg"]
        r["load_ratio"] = "0.0"
        out.append(r)
    return out


def list_all(token: str) -> list:
    """기존 문서 이름 전체. 삭제 대상이자 백업 원본이다."""
    docs, page = [], None
    while True:
        url = (f"projects/{PROJECT}/databases/(default)/documents/{COLLECTION}"
               f"?pageSize=300" + (f"&pageToken={page}" if page else ""))
        body = api(token, url)
        docs.extend(body.get("documents", []))
        page = body.get("nextPageToken")
        if not page:
            break
    return docs


def batch_write(token: str, writes: list, label: str):
    total = len(writes)
    for i in range(0, total, BATCH_LIMIT):
        chunk = writes[i:i + BATCH_LIMIT]
        api(token, f"projects/{PROJECT}/databases/(default)/documents:batchWrite",
            {"writes": chunk}, method="POST")
        done = min(i + BATCH_LIMIT, total)
        print(f"\r  {label} {done}/{total}", end="", flush=True)
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 삭제/적재한다")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup-only", action="store_true")
    ap.add_argument("--backup", default=os.path.join(HERE, "trucks_backup.json"))
    args = ap.parse_args()

    rows = load_rows()
    print(f"CSV {len(rows)}대 — {CSV_PATH}")
    for r in rows:
        print(f"  {r['truck_id']} | {r['max_payload_kg']:>6}kg | "
              f"{r['cargo_capacity_cbm']:>7}CBM | {r['spec_template_id']}")

    token = access_token()
    existing = list_all(token)
    print(f"\n기존 trucks 문서: {len(existing)}건")

    if args.dry_run:
        print("\n--dry-run: 아무것도 바꾸지 않았다.")
        return

    with open(args.backup, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False)
    print(f"백업 저장: {args.backup} "
          f"({os.path.getsize(args.backup) / 1e6:.1f}MB)")

    if args.backup_only:
        return
    if not args.apply:
        print("\n--apply 없이는 삭제하지 않는다.")
        return

    print(f"\n삭제 {len(existing)}건")
    batch_write(token, [{"delete": d["name"]} for d in existing], "삭제")

    print(f"적재 {len(rows)}건")
    batch_write(token, [{
        "update": {
            "name": f"projects/{PROJECT}/databases/(default)/documents"
                    f"/{COLLECTION}/{r['truck_id']}",
            "fields": {k: typed(k, v) for k, v in r.items()},
        }
    } for r in rows], "적재")

    left = list_all(token)
    print(f"\n완료 — trucks {len(left)}건: "
          f"{', '.join(sorted(d['name'].rsplit('/', 1)[-1] for d in left))}")


if __name__ == "__main__":
    main()
