"""pending_cargos의 터미널 필드를 출발/도착 두 축으로 옮긴다.

    terminal_code  -> origin_terminal_code
    terminal_name  -> origin_terminal_name
    (신규)          destination_terminal_code / destination_terminal_name
                    delivery_lat / delivery_lng / delivery_address

도착터미널은 원본에 없다. 체적 측정기는 상차 터미널에 놓여 있어 "어디서 실리는가"만
안다. cargo_ingest.assign_destination과 **같은 규칙**(운송장번호 SHA-1 해시로 등록
터미널 중 출발지 아닌 곳을 고름)을 써서, 이미 적재된 문서와 앞으로 적재될 문서가
같은 도착지를 갖게 한다.

    python tools/migrate_cargo_terminals.py --dry-run
    python tools/migrate_cargo_terminals.py --apply
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

PROJECT = os.getenv("GCP_PROJECT", "moveai-504903")
DOCS = f"projects/{PROJECT}/databases/(default)/documents"
BATCH_LIMIT = 500
HERE = os.path.dirname(os.path.abspath(__file__))


def access_token() -> str:
    for cmd in (["gcloud", "auth", "print-access-token"],
                [sys.executable,
                 os.path.expandvars(r"%LOCALAPPDATA%\Google\Cloud SDK"
                                    r"\google-cloud-sdk\lib\gcloud.py"),
                 "auth", "print-access-token"]):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  check=True).stdout.strip()
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
            if e.code in (429, 500, 503) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"Firestore {method} {path} 실패 {e.code}: {e.read().decode()[:400]}")


def unwrap(f: dict):
    k, v = next(iter(f.items()))
    if k == "integerValue":
        return int(v)
    if k == "doubleValue":
        return float(v)
    if k == "booleanValue":
        return bool(v)
    if k == "nullValue":
        return None
    return v


def fetch_all(token: str, collection: str) -> list:
    docs, page = [], None
    while True:
        body = api(token, f"{DOCS}/{collection}?pageSize=300"
                          + (f"&pageToken={page}" if page else ""))
        docs.extend(body.get("documents", []))
        page = body.get("nextPageToken")
        if not page:
            break
    return docs


def pick_destination(cargo_id: str, origin_code: str, pool: list):
    """cargo_ingest.assign_destination과 동일한 규칙이어야 한다."""
    usable = [t for t in pool if t["terminal_code"] != origin_code]
    if not usable:
        return None
    digest = hashlib.sha1(str(cargo_id).encode("utf-8")).digest()
    return usable[int.from_bytes(digest[:8], "big") % len(usable)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup", default=os.path.join(HERE, "pending_cargos_backup.json"))
    args = ap.parse_args()

    token = access_token()

    terminals = sorted(
        ({k: unwrap(v) for k, v in d["fields"].items()}
         for d in fetch_all(token, "terminals")),
        key=lambda t: t["terminal_code"],
    )
    print(f"등록 터미널 {len(terminals)}곳")
    if len(terminals) < 2:
        sys.exit("도착터미널을 배정하려면 등록 터미널이 2곳 이상 필요하다.")

    cargos = fetch_all(token, "pending_cargos")
    print(f"pending_cargos {len(cargos)}건")

    plan, skipped = [], 0
    for d in cargos:
        f = d["fields"]
        cargo_id = unwrap(f["cargo_id"]) if "cargo_id" in f else d["name"].rsplit("/", 1)[-1]
        origin = (unwrap(f["origin_terminal_code"]) if "origin_terminal_code" in f
                  else unwrap(f["terminal_code"]) if "terminal_code" in f else None)
        if not origin:
            skipped += 1
            continue
        origin_name = (unwrap(f["origin_terminal_name"]) if "origin_terminal_name" in f
                       else unwrap(f["terminal_name"]) if "terminal_name" in f else None)
        dest = pick_destination(cargo_id, origin, terminals)
        if dest is None:
            skipped += 1
            continue
        plan.append((d, origin, origin_name, dest))

    print(f"변환 대상 {len(plan)}건 / 건너뜀 {skipped}건")
    if plan:
        d, o, on, dest = plan[0]
        print(f"  예시 {d['name'].rsplit('/', 1)[-1]}: "
              f"출발 {o}({on}) -> 도착 {dest['terminal_code']}({dest.get('name')})")

    if args.dry_run or not args.apply:
        print("\n--apply 없이는 쓰지 않는다.")
        return

    with open(args.backup, "w", encoding="utf-8") as fp:
        json.dump(cargos, fp, ensure_ascii=False)
    print(f"백업 저장: {args.backup}")

    writes = []
    for d, origin, origin_name, dest in plan:
        fields = dict(d["fields"])
        # 옛 이름을 지운다. 남겨두면 어느 쪽이 정본인지 코드마다 갈린다.
        fields.pop("terminal_code", None)
        fields.pop("terminal_name", None)
        fields["origin_terminal_code"] = {"stringValue": origin}
        fields["origin_terminal_name"] = (
            {"stringValue": origin_name} if origin_name else {"nullValue": None})
        fields["destination_terminal_code"] = {"stringValue": dest["terminal_code"]}
        fields["destination_terminal_name"] = (
            {"stringValue": dest["name"]} if dest.get("name") else {"nullValue": None})
        fields["delivery_lat"] = {"doubleValue": dest["lat"]}
        fields["delivery_lng"] = {"doubleValue": dest["lng"]}
        fields["delivery_address"] = {
            "stringValue": dest.get("address") or dest.get("name") or ""}
        # updateMask 없이 문서 전체를 덮어써야 옛 필드가 실제로 사라진다.
        writes.append({"update": {"name": d["name"], "fields": fields}})

    for i in range(0, len(writes), BATCH_LIMIT):
        api(token, f"{DOCS}:batchWrite", {"writes": writes[i:i + BATCH_LIMIT]},
            method="POST")
        print(f"\r  갱신 {min(i + BATCH_LIMIT, len(writes))}/{len(writes)}",
              end="", flush=True)
    print("\n완료")


if __name__ == "__main__":
    main()
