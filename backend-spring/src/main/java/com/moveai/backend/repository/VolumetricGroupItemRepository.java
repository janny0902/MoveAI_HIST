package com.moveai.backend.repository;

import com.moveai.backend.entity.VolumetricGroupItem;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface VolumetricGroupItemRepository extends JpaRepository<VolumetricGroupItem, Long> {
    List<VolumetricGroupItem> findByGroupIdOrderByIdAsc(Long groupId);
    long countByGroupId(Long groupId);
}
