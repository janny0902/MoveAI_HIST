package com.moveai.backend.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "volumetric_cargo")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class VolumetricCargo {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "cargo_id", nullable = false, length = 64)
    private String cargoId;

    @Column(name = "cargo_type", length = 16)
    private String cargoType;

    @Column(name = "width_mm", nullable = false)
    private Double widthMm;

    @Column(name = "length_mm", nullable = false)
    private Double lengthMm;

    @Column(name = "height_mm", nullable = false)
    private Double heightMm;

    @Column(name = "volume_cm3", nullable = false)
    private Double volumeCm3;

    @Column(name = "volume_m3", nullable = false)
    private Double volumeM3;

    @Column(name = "depot_code", length = 32)
    private String depotCode;

    @Column(name = "scanned_at")
    private LocalDateTime scannedAt;

    @Column(name = "source_file", nullable = false, length = 64)
    private String sourceFile;

    @Column(name = "created_at")
    private LocalDateTime createdAt;
}
