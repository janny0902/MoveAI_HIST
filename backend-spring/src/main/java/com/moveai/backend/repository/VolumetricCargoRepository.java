package com.moveai.backend.repository;

import com.moveai.backend.entity.VolumetricCargo;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface VolumetricCargoRepository extends JpaRepository<VolumetricCargo, Long> {

    long countBySourceFile(String sourceFile);

    @Query("select v from VolumetricCargo v where (:source is null or v.sourceFile = :source) order by v.id")
    List<VolumetricCargo> findPool(String source, Pageable pageable);
}
