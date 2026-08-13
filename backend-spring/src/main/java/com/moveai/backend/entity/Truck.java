package com.moveai.backend.entity;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "trucks")
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class Truck {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String driverName;
    private String phone;
    private String truckNumber;
    /** 차량 톤수 (예: 5, 11, 25) */
    private Double capacityTons;
    /** 적재 가능 부피 m³ (미입력 시 톤수 기반 추정) */
    private Double capacityM3;
    /** 윙바디/카고 등 */
    private String vehicleType;

    /** false면 차량 상세 등록 필요 */
    private Boolean profileCompleted;

    private String originCode;
    private String destinationCode;
    private String originName;
    private String destinationName;

    @Column(name = "current_location_lat")
    private Double currentLat;

    @Column(name = "current_location_lng")
    private Double currentLng;

    private String status; // IDLE, MOVING, LOADING
    private Double remainingVolumePercent;

    private Double expectedAddedFillPercent;
    private Double baselineOccupiedPercent;
    private Long activeRequestId;

    private LocalDateTime lastLoginAt;
    private LocalDateTime createdAt;
}
