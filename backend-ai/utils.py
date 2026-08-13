import csv
import os
import random

# 11톤 윙바디 표준 적재 부피 (CBM) — 2.35×9.30×2.45m · 최대 11000kg
TRUCK_CAPACITY_M3_11T = 30.545


def load_cargo_from_csv(file_path: str, count: int = 100):
    """
    CSV에서 체적 샘플 추출.
    CSV W/L/H 단위: mm (택배 체적 스캔 표준)
    """
    if not os.path.exists(file_path):
        return []

    rows = []
    with open(file_path, newline="", encoding="utf-8", errors="ignore") as f:
        for row in csv.reader(f):
            if len(row) >= 5:
                rows.append(row)
    if not rows:
        return []

    sample = random.sample(rows, k=min(count, len(rows)))
    cargo_list = []
    for row in sample:
        try:
            w_mm = float(row[2])
            l_mm = float(row[3])
            h_mm = float(row[4])
        except (TypeError, ValueError):
            continue
        volume_cm3 = (w_mm * l_mm * h_mm) / 1000.0
        cargo_list.append(
            {
                "cargo_id": str(row[0]),
                "type": str(row[1]),
                "width": w_mm,
                "length": l_mm,
                "height": h_mm,
                "dim_unit": "mm",
                "volume_cm3": volume_cm3,
                "volume_m3": volume_cm3 / 1_000_000.0,
            }
        )
    return cargo_list


def calculate_total_metrics(cargo_list):
    total_volume_m3 = sum(c["volume_cm3"] for c in cargo_list) / 1_000_000
    total_count = len(cargo_list)
    fill_percent = (total_volume_m3 / TRUCK_CAPACITY_M3_11T) * 100 if TRUCK_CAPACITY_M3_11T else 0

    return {
        "total_count": total_count,
        "total_volume_m3": round(total_volume_m3, 4),
        "truck_capacity_m3": TRUCK_CAPACITY_M3_11T,
        "fill_percent_of_11t": round(fill_percent, 2),
        "total_weight_kg": round(total_count * 8.5, 2),
        "proposed_fee": total_count * 1500,
    }
