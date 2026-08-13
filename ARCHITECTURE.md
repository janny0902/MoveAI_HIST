# moveAI — 아키텍처 요약

상세: [`docs/03-architecture.md`](docs/03-architecture.md) · AI: [`docs/05-ai-spec.md`](docs/05-ai-spec.md) · 인덱스: [`docs/README.md`](docs/README.md)

---

## 한눈에

```
:20100 frontend(nginx) → Vue · /admin→React · /api→Spring:21808 · /ai→AI:21800 → PG:21432  
(별도 hist-moveai-nginx 없음 · 네트워크 moveainetwork-hist)
잔여공간: Depth Anything V2 + OpenCV(박스/철벽) + Gemini Vision 융합
브리핑·최적배차: Gemini
지도: 카카오 JS + REST directions (구간 stitch)
운행 중 복화: 20km · 동일 도착 권역 · 계획 잔여 · 도착 앞 경유
```

네트워크: `moveainetwork-hist` · Compose: `moveai-hist` (기존 30100과 병행)

`/admin`은 **적재 배정 시뮬**(CBM/중량). 기사 위치 디스패치가 아니다.  
[`docs/11-admin-integration.md`](docs/11-admin-integration.md)
