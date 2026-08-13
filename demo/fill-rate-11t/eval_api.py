"""Call /ai/analyze-image for each demo fill image (real HTTP API)."""
import glob
import json
import os
import re
import urllib.request


def post_file(path: str) -> dict:
    boundary = "----moveaiBoundary7MA4YWxkTrZu0gW"
    filename = os.path.basename(path)
    with open(path, "rb") as f:
        raw = f.read()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: image/png\r\n\r\n",
            raw,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    req = urllib.request.Request(
        "http://127.0.0.1:8000/ai/analyze-image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def main():
    rows = []
    for path in sorted(glob.glob("/tmp/fill-rate-11t/fill_*.png")):
        name = os.path.basename(path)
        m = re.search(r"fill_(\d+)pct", name)
        gt = int(m.group(1)) if m else -1
        try:
            r = post_file(path)
            occ = r.get("occupied_volume_percent")
            rem = r.get("remaining_volume_percent")
            engine = r.get("pack_engine") or r.get("engine")
            pipe = r.get("pipeline") or r.get("space_pipeline")
            space_engine = r.get("space_engine")
            reason = r.get("reasoning")
            logs = r.get("logs") or []
            gemini_lines = [x for x in logs if "gemini" in str(x).lower() or "Gemini" in str(x)]
            err = round(float(occ) - gt, 1) if occ is not None and gt >= 0 else None
            row = {
                "file": name,
                "gt": gt,
                "pred_occ": occ,
                "pred_rem": rem,
                "err": err,
                "engine": engine,
                "space_engine": space_engine,
                "pipeline": pipe,
                "reason": reason,
                "gemini_logs": gemini_lines[:4],
            }
        except Exception as e:
            row = {"file": name, "gt": gt, "error": f"{e.__class__.__name__}: {e}"}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    out = "/tmp/fill-rate-11t/eval_api_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    ok = [x for x in rows if x.get("err") is not None]
    print("---SUMMARY---", flush=True)
    if ok:
        mae = sum(abs(x["err"]) for x in ok) / len(ok)
        print(f"n={len(ok)} MAE={mae:.1f}", flush=True)
        for x in ok:
            mark = "OK" if abs(x["err"]) <= 15 else "BAD"
            print(
                f"[{mark}] GT {x['gt']:>3}% -> API {x['pred_occ']:>6}%  err={x['err']:>6}  engine={x['engine']}",
                flush=True,
            )


if __name__ == "__main__":
    main()
