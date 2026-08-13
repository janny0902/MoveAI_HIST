package com.moveai.backend.entity;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "cargo_requests")
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class CargoRequest {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String origin;
    private String destination;
    private String viaStation;

    private String originCode;
    private String viaCode;
    private String destinationCode;

    private Integer boxCount;
    @Column(name = "total_volume_m3")
    private Double totalVolumeM3;
    @Column(name = "total_weight_kg")
    private Double totalWeightKg;
    private Integer proposedFee;

    /** 약속된 추가 적재율(% of 11t) */
    private Double expectedFillPercent;
    /** 수락 시점 차량 점유율(%) */
    private Double baselineOccupiedPercent;

    private Long groupId;

    /** 관리자(matching) 체적 ID — 복화 동기화 중복 방지 */
    @Column(name = "external_cargo_id", unique = true)
    private String externalCargoId;

    /** 선착순 수락한 차량 (다기사 경쟁) */
    private Long assignedTruckId;
    private String assignedDriverName;

    private String status; // PENDING, ASSIGNED, UNMATCHED, COMPLETED
    private LocalDateTime createdAt;
}
