# moveAI 문서 인덱스 (`docs/`)

> **목적**: 현재 시연 MVP를 재현·제출용으로 설명한다.  
> **기준일**: 2026-08-13  
> **로컬**: `http://localhost:30100` (기사 `/`, 관리자 `/admin`)  
> **제출 저장소**: [janny0902/janny0902-MoveAI_HIST](https://github.com/janny0902/janny0902-MoveAI_HIST)

---

## 읽는 순서

| 순서 | 문서 | 내용 |
|------|------|------|
| 0 | [00-agent-brief.md](00-agent-brief.md) | 한 장 요약 |
| 1 | [01-rfp.md](01-rfp.md) | 요구사항 ↔ 현재 구현 |
| 2 | [02-plan.md](02-plan.md) | 구현 상태 |
| 3 | [03-architecture.md](03-architecture.md) | MSA · 컨테이너 |
| 4 | [04-features.md](04-features.md) | 기능 · 시연 규칙 |
| 5 | [05-ai-spec.md](05-ai-spec.md) | 공간 AI |
| 6 | [06-api.md](06-api.md) | API |
| 7 | [07-data-model.md](07-data-model.md) | DB |
| 8 | [08-frontend.md](08-frontend.md) | 기사 UX |
| 9 | [09-ops.md](09-ops.md) | Docker · env |
| 10 | [10-reproduction.md](10-reproduction.md) | 재현 체크 |
| 11 | [11-admin-integration.md](11-admin-integration.md) | `/admin` 적재 배정 |

루트 [README.md](../README.md)가 제출용 첫 화면이다. **기능 SSOT는 `docs/`**.

---

## 루트 MD

| 파일 | 역할 |
|------|------|
| `README.md` | 해커톤 랜딩 · 현재 시연 |
| `RFP.md` | 원본 요구 |
| `ARCHITECTURE.md` | 한 장 아키텍처 |
| `plan.md` / `answer.md` | 초기 기록. 현황은 `02-plan.md` |
