package com.moveai.backend.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "volumetric_group")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class VolumetricGroup {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "group_code", nullable = false, unique = true, length = 32)
    private String groupCode;

    @Column(name = "fill_percent", nullable = false)
    private Integer fillPercent;

    @Column(name = "target_volume_m3", nullable = false)
    private Double targetVolumeM3;

    @Column(name = "actual_volume_m3", nullable = false)
    private Double actualVolumeM3;

    @Column(name = "actual_fill_percent", nullable = false)
    private Double actualFillPercent;

    @Column(name = "box_count", nullable = false)
    private Integer boxCount;

    @Column(name = "truck_capacity_m3", nullable = false)
    private Double truckCapacityM3;

    @Column(name = "source_file", nullable = false, length = 64)
    private String sourceFile;

    @Column(name = "created_at")
    private LocalDateTime createdAt;
}
