package com.moveai.backend.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

@Entity
@Table(
        name = "terminal_distance_matrix",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_terminal_distance_od",
                columnNames = {"origin_code", "dest_code"}
        )
)
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class TerminalDistance {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "origin_code", nullable = false, length = 32)
    private String originCode;

    @Column(name = "dest_code", nullable = false, length = 32)
    private String destCode;

    @Column(name = "distance_km")
    private Double distanceKm;

    @Column(name = "duration_min")
    private Double durationMin;

    /** kakao | haversine */
    @Column(name = "source", length = 32)
    private String source;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}
