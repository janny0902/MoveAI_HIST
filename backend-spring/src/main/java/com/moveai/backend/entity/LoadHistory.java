package com.moveai.backend.entity;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "load_history")
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class LoadHistory {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long truckId;
    private Long cargoRequestId;
    private String origin;
    private String destination;
    /** 전체 운행 경로 요약 (출발→경유→도착) */
    @Column(length = 512)
    private String routeSummary;
    private String loadImageUrl;
    private Double remainingVolumePercent;
    private Double occupiedVolumePercent;
    private Double esgReductionKg;
    private Integer income;
    private Integer expense;
    private Integer netProfit;

    private LocalDateTime createdAt;
}
