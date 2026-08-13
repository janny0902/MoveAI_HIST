#!/bin/bash
set -e
sudo docker cp /tmp/_bench_optimal.py mvp-moveai-backend-ai:/tmp/_bench_optimal.py
echo "=== AI optimal-dispatch only ==="
sudo docker exec mvp-moveai-backend-ai python /tmp/_bench_optimal.py
echo "=== Spring optimal-plan (full) ==="
# truck id 1 가정
START=$(date +%s%3N)
RESP=$(sudo docker exec mvp-moveai-backend-spring sh -c 'wget -qO- --timeout=180 --header="Content-Type: application/json" --post-data="{\"truckId\":1}" http://127.0.0.1:8080/api/dispatch/optimal-plan' 2>/dev/null || true)
END=$(date +%s%3N)
echo "spring_http_ms $((END-START))"
echo "$RESP" | head -c 900
echo
