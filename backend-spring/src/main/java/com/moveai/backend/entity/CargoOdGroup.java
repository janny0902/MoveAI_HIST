package com.moveai.backend.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 기존 체적(운송장)을 출도착 터미널 쌍으로 묶은 조회용 테이블.
 * 신규 적재가 아니라, 현재 DB/API 스냅샷을 그룹화해 복화리스트에 쓴다.
 */
@Entity
@Table(
        name = "cargo_od_groups",
        uniqueConstraints = @UniqueConstraint(name = "uk_cargo_od_route", columnNames = {"route_key"})
)
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class CargoOdGroup {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 예: 200:305 */
    @Column(name = "route_key", nullable = false, length = 64)
    private String routeKey;

    @Column(name = "origin_terminal_code", length = 32)
    private String originTerminalCode;
    @Column(name = "origin_terminal_name")
    private String originTerminalName;
    @Column(name = "destination_terminal_code", length = 32)
    private String destinationTerminalCode;
    @Column(name = "destination_terminal_name")
    private String destinationTerminalName;

    /** 기사 경로 매칭용 — 터미널 코드 또는 보조 KTX */
    @Column(name = "origin_station_code", length = 32)
    private String originStationCode;
    @Column(name = "destination_station_code", length = 32)
    private String destinationStationCode;

    @Column(name = "origin_lat")
    private Double originLat;
    @Column(name = "origin_lng")
    private Double originLng;
    @Column(name = "destination_lat")
    private Double destinationLat;
    @Column(name = "destination_lng")
    private Double destinationLng;

    @Column(name = "waybill_count")
    private Integer waybillCount;
    @Column(name = "box_count")
    private Integer boxCount;
    @Column(name = "volume_m3")
    private Double volumeM3;
    @Column(name = "weight_kg")
    private Double weightKg;
    @Column(name = "freight_krw")
    private Integer freightKrw;
    @Column(name = "fill_percent_of_11t")
    private Double fillPercentOf11t;

    /**
     * 등록/집계 시 사전 계산한 차종별 점유율 JSON.
     * 예: {"1t":12.5,"11t":2.5,...} — 조회 시 기사 톤수 키만 읽음.
     */
    @Column(name = "fill_by_vehicle_json", columnDefinition = "TEXT")
    private String fillByVehicleJson;

    /** 대표 상품 요약 예: 박스 2 · 행낭 1 */
    @Column(name = "product_summary", length = 255)
    private String productSummary;

    /** 대표 적재 사진 (최근 등록분) */
    @Column(name = "photo_url", length = 512)
    private String photoUrl;

    /** 수락용 cargo_requests 연결 */
    @Column(name = "cargo_request_id")
    private Long cargoRequestId;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}
