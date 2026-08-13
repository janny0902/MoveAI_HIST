package com.moveai.backend.repository;

import com.moveai.backend.entity.LoadHistory;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface LoadHistoryRepository extends JpaRepository<LoadHistory, Long> {
    List<LoadHistory> findByTruckIdOrderByCreatedAtDesc(Long truckId);
}
