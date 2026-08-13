package com.moveai.backend.repository;

import com.moveai.backend.entity.TerminalDistance;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface TerminalDistanceRepository extends JpaRepository<TerminalDistance, Long> {
    Optional<TerminalDistance> findByOriginCodeAndDestCode(String originCode, String destCode);
}
