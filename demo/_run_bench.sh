#!/bin/bash
set -e
sudo docker cp /tmp/_bench_optimal.py mvp-moveai-backend-ai:/tmp/_bench_optimal.py
echo "=== AI optimal-dispatch only ==="
sudo docker exec mvp-moveai-backend-ai python /tmp/_bench_optimal.py
echo "=== Spring optimal-plan via nginx ==="
python3 - <<'PY'
import json, time, urllib.request
t0 = time.time()
req = urllib.request.Request(
    "http://127.0.0.1:30100/api/dispatch/optimal-plan",
    data=json.dumps({"truckId": 1}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as res:
    raw = res.read().decode()
ms = int((time.time() - t0) * 1000)
print("spring_http_ms", ms)
d = json.loads(raw)
print({k: d.get(k) for k in ("llmSource", "timingMs", "candidatesConsidered", "llmError")})
print(str(d.get("briefing", ""))[:200])
PY
