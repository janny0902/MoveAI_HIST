import argparse
import glob
import json
import os
import re
import time

import space_analyzer as sa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-gemini", action="store_true")
    ap.add_argument("--out", default="/tmp/fill-rate-11t/eval_yolo_depth.json")
    args = ap.parse_args()

    if not args.with_gemini:
        sa.analyze_occupancy_with_gemini = lambda *a, **k: None

    # YOLO 로드 스모크
    try:
        from ultralytics import YOLO
        import torch
        import torchvision
        from torchvision.ops import nms

        print(
            f"torch={torch.__version__} tv={torchvision.__version__} nms=ok",
            flush=True,
        )
        YOLO("/app/yolov8n-seg.pt")
        print("yolo-load=ok", flush=True)
    except Exception as e:
        print(f"yolo-smoke-fail={e}", flush=True)

    rows = []
    for path in sorted(glob.glob("/tmp/fill-rate-11t/fill_*.png")):
        name = os.path.basename(path)
        m = re.search(r"fill_(\d+)pct", name)
        gt = int(m.group(1)) if m else -1
        t0 = time.time()
        with open(path, "rb") as f:
            data = f.read()
        r = sa.analyze_truck_space(data, name)
        elapsed = round(time.time() - t0, 1)
        yolo_ok = not any(
            "YOLO 스킵" in x or "yolo-failed" in x for x in (r.get("logs") or [])
        )
        seg_lines = [x for x in (r.get("logs") or []) if "분할 완료" in x or "YOLO" in x]
        occ = r.get("occupied_volume_percent")
        err = round(float(occ) - gt, 1) if gt >= 0 and occ is not None else None
        row = {
            "file": name,
            "gt": gt,
            "pred_occ": occ,
            "pred_rem": r.get("remaining_volume_percent"),
            "err": err,
            "cover": r.get("cargo_cover_percent"),
            "blocked": r.get("depth_fill_blocked"),
            "mass": r.get("depth_fill_mass"),
            "engine": r.get("pack_engine") or r.get("engine"),
            "yolo_ok": yolo_ok,
            "seg_log": seg_lines[-1] if seg_lines else None,
            "sec": elapsed,
            "gemini": bool(args.with_gemini),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print("---SUMMARY---", flush=True)
    errs = [x["err"] for x in rows if x["err"] is not None]
    mae = sum(abs(e) for e in errs) / max(1, len(errs))
    print(f"MAE={mae:.1f} yolo_ok_count={sum(1 for x in rows if x['yolo_ok'])}/{len(rows)}", flush=True)
    for x in rows:
        print(
            f"{x['gt']:>3}% GT -> pred {x['pred_occ']:>6}  err={x['err']:>6}  "
            f"cover={x['cover']} yolo={x['yolo_ok']} ({x['sec']}s)",
            flush=True,
        )


if __name__ == "__main__":
    main()
