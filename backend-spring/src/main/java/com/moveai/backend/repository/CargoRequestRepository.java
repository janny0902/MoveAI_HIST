package com.moveai.backend.repository;

import com.moveai.backend.entity.CargoRequest;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.*;

public interface CargoRequestRepository extends JpaRepository<CargoRequest, Long> {
    List<CargoRequest> findByStatusOrderByCreatedAtDesc(String status);

    Optional<CargoRequest> findByExternalCargoId(String externalCargoId);

    /** 선착순 배정: PENDING일 때만 성공 (0이면 이미 배차됨) */
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("UPDATE CargoRequest c SET c.status = 'ASSIGNED', c.assignedTruckId = :truckId, c.assignedDriverName = :driverName "
            + "WHERE c.id = :id AND c.status = 'PENDING'")
    int assignIfPending(@Param("id") Long id, @Param("truckId") Long truckId, @Param("driverName") String driverName);
}
