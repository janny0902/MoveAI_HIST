package com.moveai.backend.entity;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "volumetric_group_item")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class VolumetricGroupItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "group_id", nullable = false)
    private Long groupId;

    @Column(name = "volumetric_cargo_id", nullable = false)
    private Long volumetricCargoId;

    @Column(name = "cargo_id", nullable = false, length = 64)
    private String cargoId;

    @Column(name = "cargo_type", length = 16)
    private String cargoType;

    @Column(name = "width_mm")
    private Double widthMm;

    @Column(name = "length_mm")
    private Double lengthMm;

    @Column(name = "height_mm")
    private Double heightMm;

    @Column(name = "volume_cm3", nullable = false)
    private Double volumeCm3;

    @Column(name = "volume_m3", nullable = false)
    private Double volumeM3;
}
