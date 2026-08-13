package com.moveai.backend.repository;

import com.moveai.backend.entity.VolumetricGroup;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface VolumetricGroupRepository extends JpaRepository<VolumetricGroup, Long> {
    List<VolumetricGroup> findAllByOrderByFillPercentAsc();
    Optional<VolumetricGroup> findByGroupCode(String groupCode);
}
