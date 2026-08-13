package com.moveai.backend.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/** OD 그룹에 속한 개별 운송장/박스 (단건 등록·목록용) */
@Entity
@Table(name = "cargo_od_items", indexes = {
        @Index(name = "idx_od_items_group", columnList = "od_group_id"),
        @Index(name = "idx_od_items_external", columnList = "external_cargo_id", unique = true)
})
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class CargoOdItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "od_group_id", nullable = false)
    private Long odGroupId;

    @Column(name = "external_cargo_id", length = 64)
    private String externalCargoId;

    @Column(name = "origin_terminal_code", length = 32)
    private String originTerminalCode;
    @Column(name = "destination_terminal_code", length = 32)
    private String destinationTerminalCode;

    @Column(name = "box_count")
    private Integer boxCount;
    @Column(name = "volume_m3")
    private Double volumeM3;
    @Column(name = "weight_kg")
    private Double weightKg;
    @Column(name = "freight_krw")
    private Integer freightKrw;
    @Column(name = "product_code")
    private String productCode;
    @Column(name = "product_name")
    private String productName;

    /** 그룹 사진 등 등록 이미지 URL (/uploads/...) */
    @Column(name = "photo_url", length = 512)
    private String photoUrl;

    /** WAITING | ASSIGNED | DONE */
    private String status;

    @Column(name = "created_at")
    private LocalDateTime createdAt;
}
