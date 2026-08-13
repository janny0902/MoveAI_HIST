import json
import time
import urllib.request

body = {
    "driver_origin": "Busan",
    "driver_destination": "Seoul",
    "remaining_percent": 100,
    "candidates": [
        {
            "requestId": 1,
            "origin": "Gimcheon",
            "destination": "Seoul",
            "netProfit": 120000,
            "extraDistanceKm": 12,
            "extraMinutes": 18,
            "fillPercentOf11t": 20,
            "heuristicScore": 5.1,
        },
        {
            "requestId": 2,
            "origin": "Daejeon",
            "destination": "Seoul",
            "netProfit": 90000,
            "extraDistanceKm": 8,
            "extraMinutes": 12,
            "fillPercentOf11t": 15,
            "heuristicScore": 4.2,
        },
        {
            "requestId": 3,
            "origin": "Daegu",
            "destination": "Seoul",
            "netProfit": 150000,
            "extraDistanceKm": 22,
            "extraMinutes": 30,
            "fillPercentOf11t": 25,
            "heuristicScore": 3.8,
        },
    ],
}
data = json.dumps(body).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8000/ai/optimal-dispatch",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST",
)
t0 = time.time()
with urllib.request.urlopen(req, timeout=120) as res:
    raw = res.read().decode("utf-8")
ms = int((time.time() - t0) * 1000)
print("http_ms", ms)
print(raw[:800])
