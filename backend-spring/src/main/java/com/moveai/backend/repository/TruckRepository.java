package com.moveai.backend.repository;

import com.moveai.backend.entity.Truck;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface TruckRepository extends JpaRepository<Truck, Long> {
    Optional<Truck> findByTruckNumberAndPhone(String truckNumber, String phone);
}
