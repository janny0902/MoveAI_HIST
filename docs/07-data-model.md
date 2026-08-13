# 07 — 데이터 모델

---

## 1. 개요

- 초기 SQL: `db-init/init.sql`
- JPA `ddl-auto=update`로 런타임 컬럼 확장
- 체적 CSV → `db-import` 스크립트가 `volumetric_*` 채움

---

## 2. 테이블

### trucks
| 컬럼 | 설명 |
|------|------|
| id | PK |
| driver_name, phone, truck_number | 기사/차량 |
| capacity_tons, capacity_m3, vehicle_type | 스펙 |
| profile_completed | 프로필 완료 |
| origin_code/name, destination_code/name | OD |
| current_location_lat/lng | 위치(선택) |
| status | IDLE/LOADING/MOVING 등 |
| remaining_volume_percent | 잔여 % |
| expected_added_fill_percent, baseline_occupied_percent | 상차 검증용 |
| active_request_id | 진행 중 요청 |

### cargo_requests
| 컬럼 | 설명 |
|------|------|
| origin/destination/via (+ codes) | 경로 |
| box_count, total_volume_m3, total_weight_kg | 물량 |
| proposed_fee | 요금 |
| expected_fill_percent | 11톤 대비 |
| assigned_truck_id | 수락 트럭 |
| status | PENDING / ASSIGNED / ... |

### load_history
적재 분석 + **정산 행**으로도 사용.

| 컬럼 | 설명 |
|------|------|
| truck_id, cargo_request_id | 연결 |
| load_image_url | 파일명 |
| remaining/occupied_volume_percent | 실측 |
| income, expense, net_profit | 정산 |
| esg_reduction_kg | ESG |
| route_summary | 표시용 경로 문자열 |
| created_at | 시각 |

### volumetric_cargo
개별 박스 체적 (mm, cm3, m3, source_file).

### volumetric_group
`fill_percent` ∈ {5,10,30,50,90}, 목표/실부피, box_count, truck_capacity_m3=50.

### volumetric_group_item
group ↔ cargo 연결.

---

## 3. 시드·상수

- 트럭 시드 INSERT 없음 — 로그인 시 생성
- KTX 역 좌표/코드: Spring 코드 내 stations 목록 (BUSAN, SEOUL, GIMCHEON 등)
- 용량: **50 m³**

---

## 4. CSV

경로: `Volumetric data/origin 체적.csv` (및 학습 샘플)  
컨테이너: `/data/volumetric` 마운트  
import: `db-init/import_volumetric.sh`, `build_volumetric_groups.sh`

대용량 → git에 넣지 않을 수 있음. 배포 시 scp 필요.

---

## 5. 상태 전이

```
cargo_requests: PENDING --accept--> ASSIGNED
trucks.remaining: upload/analyze로 갱신
load_history: upload 시 실측 행 / accept 시 정산 행(구현에 따라 필드 채움)
```
