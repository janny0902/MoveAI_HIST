package com.moveai.backend.repository;

import com.moveai.backend.entity.CargoOdGroup;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface CargoOdGroupRepository extends JpaRepository<CargoOdGroup, Long> {
    Optional<CargoOdGroup> findByRouteKey(String routeKey);

    Optional<CargoOdGroup> findByCargoRequestId(Long cargoRequestId);

    List<CargoOdGroup> findAllByOrderByVolumeM3Desc();
}
