package com.moveai.backend.repository;

import com.moveai.backend.entity.CargoOdItem;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface CargoOdItemRepository extends JpaRepository<CargoOdItem, Long> {
    List<CargoOdItem> findByOdGroupIdOrderByIdAsc(Long odGroupId);

    Optional<CargoOdItem> findByExternalCargoId(String externalCargoId);

    long countByOdGroupId(Long odGroupId);
}
