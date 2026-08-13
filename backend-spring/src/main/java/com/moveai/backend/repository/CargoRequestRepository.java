package com.moveai.backend.repository;

import com.moveai.backend.entity.CargoRequest;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CargoRequestRepository extends JpaRepository<CargoRequest, Long> {
    List<CargoRequest> findByStatusOrderByIdDesc(String status);
}
