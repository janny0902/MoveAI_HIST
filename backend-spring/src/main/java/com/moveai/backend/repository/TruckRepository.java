package com.moveai.backend.repository;

import com.moveai.backend.entity.Truck;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TruckRepository extends JpaRepository<Truck, Long> {
    Optional<Truck> findByPhoneAndTruckNumber(String phone, String truckNumber);
}
